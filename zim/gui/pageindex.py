# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''This module contains a class to display an index of pages.
This widget is used primarily in the side pane of the main window,
but also e.g. for the page lists in the search dialog.
'''

import gobject
import gtk
import pango

from zim.index import IndexPath
from zim.gui.widgets import BrowserTreeView

NAME_COL = 0  # column with short page name (page.basename)

class PageTreeStore(gtk.GenericTreeModel):
	'''FIXME

	Note: Be aware that in this interface there are two classes both referred
	to as "paths". The first is gtk.TreePath and the second is
	zim.notebook.Path . When a TreePath is intended the argument is called
	explicitly "treepath", while arguments called "path" refer to a zim Path.

	TODO see python gtk-2.0 tutorial for remarks about reference leaking !
	'''

	def __init__(self, index):
		gtk.GenericTreeModel.__init__(self)
		self.index = index
		index.connect('page-inserted',
			lambda o, p: self.emit('row-inserted',
				self.get_treepath(p), self.create_tree_iter(p)))
		index.connect('page-updated',
			lambda o, p: self.emit('row-changed',
				self.get_treepath(p), self.create_tree_iter(p)))
		index.connect('page-haschildren-toggled',
			lambda o, p: self.emit('row-has-child-toggled',
				self.get_treepath(p), self.create_tree_iter(p)))
		#~ index.connect('page-dropped',
			#~ lambda o, p: self.emit('row-deleted', self.get_treepath(p)))
			# TODO: how to get treepath for a droped page ??

	def on_get_flags(self):
		return 0 # no flags

	def on_get_n_columns(self):
		return 1 # only one column

	def on_get_column_type(self, index):
		#~ print '>> on_get_column_type', index
		assert index == 0
		return gobject.TYPE_STRING

	def on_get_iter(self, treepath):
		'''Returns an IndexPath for a TreePath or raises ValueError'''
		# Path (0,) is the first item in the root namespace
		# Path (2, 4) is the 5th child of the 3rd item
		#~ print '>> on_get_iter', treepath
		iter = None
		for i in treepath:
			iter = self.on_iter_nth_child(iter, i)
			if iter is None:
				raise ValueError, 'Not a valid TreePath %s' % str(treepath)
		return iter

	def get_treepath(self, path):
		'''Returns a TreePath for a given IndexPath'''
		# There is no TreePath class in pygtk,just return tuple of integers
		# FIXME this method looks quite inefficient, can we optimize it ?
		if not isinstance(path, IndexPath):
			path = self.index.lookup_path(path)
			if path is None or path.isroot:
				raise ValueError
		treepath = []
		for parent in path.parents():
			pagelist = self.index.list_pages(parent)
			treepath.insert(0, pagelist.index(path))
			path = parent
		return tuple(treepath)

	on_get_path = get_treepath # alias for GenericTreeModel API

	def get_indexpath(self, iter):
		'''Returns an IndexPath for a TreeIter'''
		return self.get_user_data(iter)

	def on_get_value(self, path, column):
		'''Returns the data for a specific column'''
		#~ print '>> on_get_value', path, column
		assert column == 0
		return path.basename

	def on_iter_next(self, path):
		'''Returns the IndexPath for the next row on the same level or None'''
		# Only within one namespace, so not the same as index.get_next()
		#~ print '>> on_iter_next', path
		if not path._pagelist_ref is None:
			pagelist = path._pagelist_ref
			i = path._pagelist_index + 1
		else:
			pagelist = self.index.list_pages(path.get_parent())
			i = pagelist.index(path) + 1

		if i >= len(pagelist):
			return None
		else:
			next = pagelist[i]
			next._pagelist_ref = pagelist
			next._pagelist_index = i
			return next

	def on_iter_children(self, path=None):
		'''Returns an indexPath for the first child below path or None.
		If path is None returns the first top level IndexPath.
		'''
		#~ print '>> on_iter_children', path
		pagelist = self.index.list_pages(path)
		if pagelist:
			child = pagelist[0]
			child._pagelist_ref = pagelist
			child._pagelist_index = 0
			return child
		else:
			return None

	def on_iter_has_child(self, path):
		'''Returns True if indexPath path has children'''
		if not path.hasdata:
			path = self.index.lookup_path(path)
		return path.haschildren

	def on_iter_n_children(self, path=None):
		'''Returns the number of children in a namespace. As a special case,
		when page is None the number of pages in the root namespace is given.
		'''
		pagelist = self.index.list_pages(path)
		return len(pagelist)

	def on_iter_nth_child(self, path, n):
		'''Returns the nth child for a given IndexPath or None.
		As a special case path can be None to get pages in the root namespace.
		'''
		#~ print '>> on_iter_nth_child', path, n
		pagelist = self.index.list_pages(path)
		if n >= len(pagelist):
			return None
		else:
			child = pagelist[n]
			child._pagelist_ref = pagelist
			child._pagelist_index = n
			return child

	def on_iter_parent(self, child):
		'''Returns a IndexPath for parent node of child or None'''
		parent = child.get_parent()
		if parent.isroot:
			return None
		else:
			return parent


class PageTreeView(BrowserTreeView):
	'''Wrapper for a TreeView showing a list of pages.'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'page-activated': (gobject.SIGNAL_RUN_LAST, None, (object,)),
	}

	def __init__(self, app):
		BrowserTreeView.__init__(self)

		self.app = app
		self.app.connect('open-page', lambda o, p, r: self.select_page(p))
		self.app.connect_after('open-notebook', self.do_set_notebook)
		if not self.app.notebook is None:
			self.do_set_notebook(self.app, self.app.notebook)

		cell_renderer = gtk.CellRendererText()
		cell_renderer.set_property('ellipsize', pango.ELLIPSIZE_END)
		column = gtk.TreeViewColumn('_pages_', cell_renderer, text=NAME_COL)
		self.append_column(column)
		self.set_headers_visible(False)

		# TODO drag & drop stuff
		# TODO popup menu for pages - share with e.g. pathbar buttons

	def do_set_notebook(self, app, notebook):
		self.set_model(PageTreeStore(notebook.index))
		if not app.page is None:
			self.select_page(app.page)

	def do_row_activated(self, treepath, column):
		'''Handler for the row-activated signal, emits page-activated'''
		model = self.get_model()
		iter = model.get_iter(treepath)
		path = model.get_indexpath(iter)
		self.emit('page-activated', path)

	def do_page_activated(self, path):
		'''Handler for the page-activated signal, calls app.open_page()'''
		self.app.open_page(path)

	def do_key_press_event(self, event):
		'''Handler for key presses'''
		if BrowserTreeView.do_key_press_event(self, event):
			return True

		try:
			key = chr(event.keyval)
		except ValueError:
			return False

		if event.state == gtk.gdk.CONTROL_MASK:
			if   key == 'c':
				print 'TODO copy location'
			elif key == 'l':
				print 'TODO insert link'
			else:
				return False
		else:
			return False

	def do_button_release_event(self, event):
		'''Handler for button-release-event, triggers popup menu'''
		if event.button == 3:
			self.emit('popup-menu')# FIXME do we need to pass x/y and button ?
			return True
		else:
			return BrowserTreeView.do_button_release_event(self, event)

	def do_popup_menu(self): # FIXME do we need to pass x/y and button ?
		print 'TODO: trigger popup for page'
		return True

	def select_page(self, path):
		'''Select a page in the treeview, connected to the open-page signal'''
		model, iter = self.get_selection().get_selected()
		if model is None:
			return # index not yet initialized ...
		#~ if not iter is None and model[iter][PAGE_COL] == pagename:
			#~ return  # this page was selected already

		# TODO unlist temporary listed items
		# TODO temporary list new item if page does not exist

		path = self.app.notebook.index.lookup_path(path)
		if path is None:
			pass # TODO temporary list the thing in the index
		else:
			treepath = model.get_treepath(path)
			self.expand_to_path(treepath)
			self.get_selection().select_path(treepath)
			self.set_cursor(treepath)
			self.scroll_to_cell(treepath)


# Need to register classes defining gobject signals
gobject.type_register(PageTreeView)


class PageIndex(gtk.ScrolledWindow):

	def __init__(self, app):
		gtk.ScrolledWindow.__init__(self)
		self.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
		self.set_shadow_type(gtk.SHADOW_IN)

		self.treeview = PageTreeView(app)
		self.add(self.treeview)

	def grab_focus(self):
		self.treeview.grab_focus()