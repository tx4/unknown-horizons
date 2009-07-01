# ###################################################
# Copyright (C) 2009 The Unknown Horizons Team
# team@unknown-horizons.org
# This file is part of Unknown Horizons.
#
# Unknown Horizons is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the
# Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
# ###################################################

import operator
import weakref
import random
import logging

import horizons.main

from horizons.world.storageholder import StorageHolder
from horizons.util import WorldObject
from horizons.world.pathfinding.pather import BuildingCollectorPather
from horizons.ext.enum import Enum
from horizons.world.units.unit import Unit

class Collector(StorageHolder, Unit):
	"""Base class for every collector. Does not depend on any home building.
	"""
	log = logging.getLogger("world.units.collector")

	WORK_DURATION = 16 # time how long a collector predends to work at target in ticks

	# all states, any (subclass) instance may have. Keeping a list in one place
	# is important, because every state must have a distinct number.
	# Handling of subclass specific states is done by subclass.
	states = Enum('idle', 'moving_to_target', 'working', 'moving_home', \
									'waiting_for_animal_to_stop', 'stopped', 'no_job_walking_randomly',
									'no_job_waiting')

	def __init__(self, x, y, slots = 1, size = 4, start_hidden=True, **kwargs):
		super(Collector, self).__init__(slots = slots, \
																		size = size, \
																		x = x, \
																		y = y, \
																		**kwargs)

		self.inventory.limit = size;
		# TODO: use different storage to support multiple slots. see StorageHolder

		self.__init(self.states.idle, start_hidden)

		# start searching jobs just when construction (of subclass) is completed
		horizons.main.session.scheduler.add_new_object(self.search_job, self, 1)

	def __init(self, state, start_hidden):
		self.state = state
		self.start_hidden = start_hidden
		if self.start_hidden:
			self.hide()

		self.job = None # here we store the current job as Job object

	def save(self, db):
		super(Collector, self).save(db)

		# save state and remaining ticks for next callback
		# retrieve remaining ticks according current callback according to state
		current_callback = None
		remaining_ticks = None
		if self.state == self.states.idle:
			current_callback = self.search_job
		elif self.state == self.states.working:
			current_callback = self.finish_working
		if current_callback is not None:
			calls = horizons.main.session.scheduler.get_classinst_calls(self, current_callback)
			assert(len(calls) == 1)
			remaining_ticks = calls.values()[0]

		db("INSERT INTO collector(rowid, state, remaining_ticks, start_hidden) VALUES(?, ?, ?, ?)", \
			 self.getId(), self.state.index, remaining_ticks, self.start_hidden)

		# save the job
		if self.job is not None and self.job.object is not None:
			db("INSERT INTO collector_job(rowid, object, resource, amount) VALUES(?, ?, ?, ?)", \
				 self.getId(), self.job.object.getId(), self.job.res, self.job.amount)

	def load(self, db, worldid):
		super(Collector, self).load(db, worldid)

		# load collector properties
		state_id, remaining_ticks, start_hidden = \
						db("SELECT state, remaining_ticks, start_hidden FROM COLLECTOR \
						   WHERE rowid = ?", worldid)[0]
		self.__init(self.states[state_id], start_hidden)

		# load job
		job_db = db("SELECT object, resource, amount FROM collector_job WHERE rowid = ?", \
								worldid)
		if(len(job_db) > 0):
			job_db = job_db[0]
			self.job = Job(WorldObject.get_object_by_id(job_db[0]), job_db[1], job_db[2])

		self.apply_state(self.state, remaining_ticks)

	def remove(self):
		"""Removes the instance. Useful when the home building is destroyed"""
		self.log.debug("Collector %s: remove called", self.getId())
		# remove from target collector list
		if self.job is not None and self.job.object is not None:
			self.job.object._Provider__collectors.remove(self)

		self.hide() # now wait for gc


	def apply_state(self, state, remaining_ticks = None):
		"""Takes actions to set collector to a state. Useful after loading.
		@param state: EnumValue from states
		@param remaining_ticks: ticks after which current state is finished
		"""
		if state == self.states.idle:
			# we do nothing, so schedule a new search for a job
			horizons.main.session.scheduler.add_new_object(self.search_job, self, remaining_ticks)
		elif state == self.states.moving_to_target:
			# we are on the way to target, so save the job
			self.setup_new_job()
			# and notify us, when we're at target
			self.add_move_callback(self.begin_working)
			self.show()
		elif state == self.states.working:
			# we are at the target and work
			# register the new job
			self.setup_new_job()
			# job finishes in remaining_ticks ticks
			horizons.main.session.scheduler.add_new_object(self.finish_working, self, remaining_ticks)

	def setup_new_job(self):
		"""Executes the necessary actions to begin a new job"""
		self.job.object._Provider__collectors.append(self)

	def search_job(self):
		"""Search for a job, only called if the collector does not have a job.
		If no job is found, a new search will be scheduled in 32 ticks."""
		self.log.debug("Collector %s search job", self.getId())

		self.job = self.get_job()
		if self.job is None:
			self.handle_no_possible_job()
		else:
			self.begin_current_job()

	def handle_no_possible_job(self):
		"""Called when we can't find a job. default is to wait and try again in 2 secs"""
		self.log.debug("Collector %s: no possible job, retry in 2 secs", self.getId())
		horizons.main.session.scheduler.add_new_object(self.search_job, self, 32)

	def get_home_inventory(self):
		"""Returns inventory where collected res will be stored.
		This could be the inventory of a home_building, or it's own.
		"""
		raise NotImplementedError

	def get_colleague_collectors(self):
		"""Returns a list of collectors, that work for the same "inventory"."""
		return []

	def get_job(self):
		"""Returns the next job or None"""
		raise NotImplementedError

	def check_possible_job_target(self, target, res):
		"""Checks out if we could get res from target.
		Does _not_ check for anything else (e.g. if we are able to walk there).
		@param target: possible target. buildings are supported, support for more can be added.
		@param res: resource id
		@return: instance of Job or None, if we can't collect anything
		"""
		res_amount = target.inventory[res]
		if res_amount <= 0:
			return None

		inventory = self.get_home_inventory()

		# get sum of picked up resources by other collectors for this res
		total_pickup_amount = sum([ collector.job.amount for collector in \
									target._Provider__collectors if \
									collector.job.res == res ])
		if total_pickup_amount > res_amount:
			return None

		# check if other collectors get this resource, because our inventory could
		# get full if they arrive.
		total_registered_amount_consumer = sum([ collector.job.amount for collector in \
												 self.get_colleague_collectors() if \
												 collector.job is not None and \
												 collector.job.res == res ])

		# check if there are resources left to pickup
		inventory_space_for_res = inventory.get_limit(res) - \
														(total_registered_amount_consumer + inventory[res])
		if inventory_space_for_res <= 0:
			return None

		# create a new job
		return Job(target, res, min(res_amount - total_pickup_amount, inventory_space_for_res))

	def begin_current_job(self):
		"""Starts executing the current job by registering itself and moving to target."""
		self.log.debug("Collector %s begins job at "+str(self.job.object.position), self.getId())
		self.setup_new_job()
		self.show()
		assert self.check_move(self.job.object.position)
		self.move(self.job.object.position, self.begin_working)
		self.state = self.states.moving_to_target
		self.log.debug("Collector %s began job", self.getId())

	def begin_working(self):
		"""Pretends that the collector works by waiting some time. finish_working is
		called after that time."""
		self.log.debug("Collector %s begins working", self.getId())
		if self.job.object is not None:
			horizons.main.session.scheduler.add_new_object(self.finish_working, self, \
																										 self.WORK_DURATION)
			self.state = self.states.working
		else:
			self.reroute()

	def finish_working(self):
		"""Called when collector has stayed at the target for a while.
		Picks up the resources."""
		self.log.debug("Collector %s finished working", self.getId())
		if self.job.object is not None:
			self.act("idle", self._instance.getFacingLocation(), True)
			# transfer res
			self.transfer_res()
			# deregister at the target we're at
			self.job.object._Provider__collectors.remove(self)
		else:
			self.reroute()

	def transfer_res(self):
		"""Transfers resources from target to collector inventory"""
		self.log.debug("Collector %s transfer_res", self.id)
		res_amount = self.job.object.pickup_resources(self.job.res, self.job.amount)
		if res_amount != self.job.amount:
			self.log.warning("collector %s picked up %s of res %s at (%s, %s), planned was %s",  \
				self.getId(), res_amount, self.job.res, \
				self.job.target.getId(), self.job.target, \
				self.job.amount)
		self.inventory.alter(self.job.res, res_amount)

	def reroute(self):
		"""Reroutes the collector to a different job.
		Can be called the current job can't be executed any more"""
		raise NotImplementedError

	def end_job(self):
		"""Contrary to setup_new_job"""
		# he finished the job now
		# before the new job can begin this will be executed
		self.log.debug("Collector %s end_job - waiting for new search_job", self.getId())
		if self.start_hidden:
			self.hide()
		horizons.main.session.scheduler.add_new_object(self.search_job , self, 32)
		self.state = self.states.idle

	def get_best_possible_job(self, jobs):
		"""Return best possible job from jobs.
		"Best" means that the job is highest when the job list was sorted.
		"Possible" means that we can find a path there.
		@param jobs: unsorted list of Job instances
		@return: selected Job instance from list or None if no jobs are possible."""
		# sort job list
		jobs = self.sort_jobs(jobs)

		# check if we can move to that targets
		for job in jobs:
			if self.check_move(job.object.position):
				return job
		return None

	def sort_jobs(self, jobs):
		"""Sorts the jobs for further processing. This has been moved to a seperate function so it
		can be overwritten by subclasses. A building collector might sort after a specific rating,
		a lumberjack might just take a random tree.
		@param jobs: list of Job instances that should be sorted an then returned.
		@return: sorted list of Job instances."""
		return self.sort_jobs_rating(jobs)

	def sort_jobs_rating(self, jobs):
		"""Sorts jobs by job rating (call this in sort_jobs if it fits to your subclass)"""
		jobs.sort(key=operator.attrgetter('rating') )
		jobs.reverse()
		return jobs

	def sort_jobs_random(self, jobs):
		"""Sorts jobs randomly (call this in sort_jobs if it fits to your subclass)"""
		random.shuffle(jobs)
		return jobs

	def sort_jobs_amount(self, jobs):
		"""Sorts the jobs by the amount of resources available"""
		jobs.sort(key=operator.attrgetter('amount'), reverse=True)
		return jobs

	def create_pather(self):
		return BuildingCollectorPather(self)


class Job(object):
	"""Data structure for storing information of collector jobs"""
	def __init__(self, obj, res, amount):
		self._object = weakref.ref(obj)
		self.res = res
		self.amount = amount

		# this is rather a dummy
		self.rating = amount

	@property
	def object(self):
		return self._object()

	def __str__(self):
		return "Job res: %i amount: %i" % (self.res, self.amount)