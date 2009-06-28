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

import pychan
import horizons.main

from tabinterface import TabInterface
from horizons.gui.tradewidget import TradeWidget

class InventoryTab(TabInterface):

	def __init__(self, instance = None, widget = 'tab_widget/tab_stock.xml'):
		super(InventoryTab, self).__init__(widget = widget)
		self.instance = instance
		self.init_values()
		self.button_up_image = 'content/gui/images/icons/hud/common/inventory_u.png'
		self.button_active_image = 'content/gui/images/icons/hud/common/inventory_a.png'
		self.button_down_image = 'content/gui/images/icons/hud/common/inventory_d.png'
		self.button_hover_image = 'content/gui/images/icons/hud/common/inventory_h.png'

	def refresh(self):
		"""This function is called by the TabWidget to redraw the widget."""
		self.widget.findChild(name='inventory').inventory = self.instance.inventory

	def show(self):
		if not self.instance.inventory.hasChangeListener(self.refresh):
			self.instance.inventory.addChangeListener(self.refresh)
		super(InventoryTab, self).show()

	def hide(self):
		if self.instance.inventory.hasChangeListener(self.refresh):
			self.instance.inventory.removeChangeListener(self.refresh)
		super(InventoryTab, self).hide()

class ShipInventoryTab(InventoryTab):

	def __init__(self, instance = None):
		super(ShipInventoryTab, self).__init__(
			widget = 'tab_widget/tab_stock_ship.xml',
			instance = instance
		)
		self.button_up_image = 'content/gui/images/icons/hud/common/inventory_u.png'
		self.button_active_image = 'content/gui/images/icons/hud/common/inventory_a.png'
		self.button_down_image = 'content/gui/images/icons/hud/common/inventory_d.png'
		self.button_hover_image = 'content/gui/images/icons/hud/common/inventory_h.png'

	def refresh(self):
		branches = horizons.main.session.world.get_branch_offices(self.instance.position, self.instance.radius)
		if len(branches) > 0:
			events = { 'trade': pychan.tools.callbackWithArguments(horizons.main.session.ingame_gui.show_menu, TradeWidget(self.instance)) }
			self.widget.mapEvents(events)
			self.widget.findChild(name='bg_button').set_active()
			self.widget.findChild(name='trade').set_active()
		else:
			events = { 'trade': None }
			self.widget.mapEvents(events)
			self.widget.findChild(name='bg_button').set_inactive()
			self.widget.findChild(name='trade').set_inactive()
		super(ShipInventoryTab, self).refresh()