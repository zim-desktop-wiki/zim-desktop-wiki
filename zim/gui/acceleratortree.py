# -*- coding: utf8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

#~ Build editable treeview of menu items + accelerators
#~
#~ Just getting action names does not give menu structure,
#~ so walk the menu.
#~
#~ Menus are containers, have a foreach
#~ Menutitems are bin, can have submenu
#~
#~ Get label using get_child() etc (probably gives a box with icon,
#~ label, accel, etc.)
#~
#~ Test get_submenu(),
#~ if is None: leaf item, get accelerator
#~ elif value: recurs
#~
#~ To get the accelerator:
#~ accel_path = menuitem.get_accel_path() (make sure this is not the mnemonic..)
#~ key, mod = gtk.accel_map_lookup_entry(accel_path)
#~
#~ To get / set accelerator labels in the UI use:
#~ gtk.accelerator_name() to get a name to display
#~
#~ To parse name set by user
#~ gtk.accelerator_parse()
#~ gtk.accelerator_valid()
#~
#~ To change the accelerator:
#~ Maybe first unlock path in accel_map and unlock the actiongroup..
#~ gtk.accel_map.change_entry(accel_path, key, mods, replace=True)
#~ check return value
#~
#~ To get updates for ui use:
#~ gtk.accel_map_get().connect('changed', func(o, accel_path, key, mods))
#~ This way we also get any accelerators that were deleted as result of
#~ replace=True
