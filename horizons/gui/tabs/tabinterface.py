# ###################################################
# Copyright (C) 2008-2013 The Unknown Horizons Team
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

from horizons.gui.util import load_uh_widget
from horizons.util.changelistener import metaChangeListenerDecorator
from horizons.util.pychanchildfinder import PychanChildFinder
from horizons.util.python.callback import Callback
from horizons.extscheduler import ExtScheduler

@metaChangeListenerDecorator('remove')
class TabInterface(object):
	"""
	The TabInterface should be used by all classes that represent Tabs for the
	TabWidget.

	It is important that the currently used widget by the tab is always set to
	self.widget, to ensure proper functionality.
	If you want to override the TabButton image used for the tab, you also have
	to set the button_image_{up,down,hover} variables.

	Use the refresh() method to implement any redrawing of the widget. The
	TabWidget will call this method based on callbacks. If you set any callbacks
	yourself, make sure you get them removed when the widget is deleted.

	Make sure to call the init_values() function after you set self.widget, to
	ensure proper initialization of needed properties.
	"""

	"""
	Whether to load the tab only when it's shown.
	If True, self.widget will only be valid after _lazy_loading_init, which
	is guaranteed to be executed before show(), refresh() and the like.
	Usually, you will want to overwrite _lazy_loading_init and call the super impl as first step.
	"""
	lazy_loading = False

	scheduled_update_delay = 0.4 # seconds, update after this time when an update is scheduled

	def __init__(self, widget=None, icon_path='images/tabwidget/tab', **kwargs):
		"""
		@param widget: filename of a widget. Set this to None if you create your own widget at self.widget
		@param icon_path: Where to look for ImageButton icons. Note: this is a `path` attribute!
		"""
		super(TabInterface, self).__init__()
		if widget is not None:
			if not self.__class__.lazy_loading:
				self.widget = self._load_widget(widget)
			else:
				self.widget = widget
		else:
			# set manually by child
			self.widget = None

		# Regular `image` paths for Icon
		self.button_background_image = 'content/gui/images/tabwidget/tab_dark.png'
		self.button_background_image_active = 'content/gui/images/tabwidget/tab_active_xxl.png'

		# `path` attribute for ImageButton, i.e. without 'content/gui/' and '.png'
		self.path = icon_path
		# the active tab image has no special down or hover images, so this works with `path` too
		self.path_active = icon_path + '_a'

		self._refresh_scheduled = False

	def init_values(self):
		"""Call this method after the widget has been initialized."""
		pass

	def show(self):
		"""Shows the current widget"""
		self.widget.show()

	def hide(self):
		"""Hides the current widget"""
		self.widget.hide()

		if self._refresh_scheduled:
			ExtScheduler().rem_all_classinst_calls(self)
			self._refresh_scheduled = False

	def is_visible(self):
		self.ensure_loaded()
		# naming convention clash: python vs c++
		return self.widget.isVisible()

	def refresh(self):
		"""This function is called by the TabWidget to redraw the widget."""
		pass

	def _schedule_refresh(self):
		"""Schedule a refresh soon, dropping all other refresh request, that appear until then.
		This saves a lot of CPU time, if you have a huge island, or play on high speed."""
		if not self._refresh_scheduled:
			self._refresh_scheduled = True
			def unset_flag():
				# set the flag here and not in refresh() since we can't be sure whether
				# refresh() of this class will be reached or a subclass will not call super()
				self._refresh_scheduled = False
			ExtScheduler().add_new_object(Callback.ChainedCallbacks(unset_flag, self.refresh),
			                              self, run_in=self.__class__.scheduled_update_delay)

	@classmethod
	def shown_for(self, instance):
		"""Method for fine-grained control of which tabs to show.
		@return: whether this tab should really be shown for this instance"""
		return True

	def ensure_loaded(self):
		"""Called when a tab is shown, acts as hook for lazy loading"""
		if self.__class__.lazy_loading and not hasattr(self, "_lazy_loading_loaded"):
			self._lazy_loading_init()
			self._lazy_loading_loaded = True

	def _lazy_loading_init(self):
		"""Called when widget is initialized for lazily initialized tabs.
		You may want to overwrite this in the subclass."""
		self.widget = self._load_widget(self.widget)
		self.init_values()

	def _load_widget(self, widget):
		widget = load_uh_widget(widget)
		widget.child_finder = PychanChildFinder(widget)
		return widget

	def _get_position(self):
		return self.widget.position

	def _set_position(self, value):
		"""Sets the widgets position to tuple *value*"""
		self.widget.position = value

	# Shortcut to set and retrieve the widget's current position.
	position = property(_get_position, _set_position)

	def __del__(self):
		"""Do cleanup work here."""
		self.widget = None
