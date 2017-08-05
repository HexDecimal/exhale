########################################################################################
# This file is part of exhale.  Copyright (c) 2017, Stephen McDowell.                  #
# Full BSD 3-Clause license available here:                                            #
#                                                                                      #
#                     https://github.com/svenevs/exhale/LICENSE.md                     #
########################################################################################

from . import configs
from . import parse
from . import utils
from .utils import exclaimError, kindAsBreatheDirective, qualifyKind, specificationsForKind, AnsiColors

import re
import os
import itertools
import textwrap
from bs4 import BeautifulSoup

try:
    # Python 2 StringIO
    from cStringIO import StringIO
except ImportError:
    # Python 3 StringIO
    from io import StringIO

__all__       = ["ExhaleRoot", "ExhaleNode"]
__name__      = "graph"
__docformat__ = "reStructuredText"


########################################################################################
#
##
###
####
##### Graph representation.
####
###
##
#
########################################################################################
class ExhaleNode:
    '''
    A wrapper class to track parental relationships, filenames, etc.

    :Parameters:
        ``breatheCompound`` (breathe.compound)
            The Breathe compound object we will use to gather the name, chilren, etc.

    :Attributes:
        ``compound`` (breathe.compound)
            The compound discovered from breathe that we are going to track.

        ``kind`` (str)
            The string returned by the ``breatheCompound.get_kind()`` method.  Used to
            qualify this node throughout the framework, as well as for hierarchical
            sorting.

        ``name`` (str)
            The string returned by the ``breatheCompound.get_name()`` method.  This name
            will be fully qualified --- ``class A`` inside of ``namespace n`` will have
            a ``name`` of ``n::A``.  Files and directories may have ``/`` characters as
            well.

        ``refid`` (str)
            The reference ID as created by Doxygen.  This will be used to scrape files
            and see if a given reference identification number should be associated with
            that file or not.

        ``children`` (list)
            A potentially empty list of ``ExhaleNode`` object references that are
            considered a child of this Node.  Please note that a child reference in any
            ``children`` list may be stored in **many** other lists.  Mutating a given
            child will mutate the object, and therefore affect other parents of this
            child.  Lastly, a node of kind ``enum`` will never have its ``enumvalue``
            children as it is impossible to rebuild that relationship without more
            Doxygen xml parsing.

        ``parent`` (ExhaleNode)
            If an ExhaleNode is determined to be a child of another ExhaleNode, this
            node will be added to its parent's ``children`` list, and a reference to
            the parent will be in this field.  Initialized to ``None``, make sure you
            check that it is an object first.

            .. warning::
               Do not ever set the ``parent`` of a given node if the would-be parent's
               kind is ``"file"``.  Doing so will break many important relationships,
               such as nested class definitions.  Effectively, **every** node will be
               added as a child to a file node at some point.  The file node will track
               this, but the child should not.

        The following three member variables are stored internally, but managed
        externally by the :class:`exhale.ExhaleRoot` class:

        ``file_name`` (str)
            The name of the file to create.  Set to ``None`` on creation, refer to
            :func:`exhale.ExhaleRoot.initializeNodeFilenameAndLink`.

        ``link_name`` (str)
            The name of the reStructuredText link that will be at the top of the file.
            Set to ``None`` on creation, refer to
            :func:`exhale.ExhaleRoot.initializeNodeFilenameAndLink`.

        ``title`` (str)
            The title that will appear at the top of the reStructuredText file
            ``file_name``. When the reStructuredText document for this node is being
            written, the root object will set this field.

        The following two fields are used for tracking what has or has not already been
        included in the hierarchy views.  Things like classes or structs in the global
        namespace will not be found by :func:`exhale.ExhaleNode.inClassView`, and the
        ExhaleRoot object will need to track which ones were missed.

        ``in_class_view`` (bool)
            Whether or not this node has already been incorporated in the class view.

        ``in_file_view`` (bool)
            Whether or not this node has already been incorporated in the file view.

        This class wields duck typing.  If ``self.kind == "file"``, then the additional
        member variables below exist:

        ``namespaces_used`` (list)
            A list of namespace nodes that are either defined or used in this file.

        ``includes`` (list)
            A list of strings that are parsed from the Doxygen xml for this file as
            include directives.

        ``included_by`` (list)
            A list of (refid, name) string tuples that are parsed from the Doxygen xml
            for this file presenting all of the other files that include this file.
            They are stored this way so that the root class can later link to that file
            by its refid.

        ``location`` (str)
            A string parsed from the Doxygen xml for this file stating where this file
            is physically in relation to the *Doxygen* root.

        ``program_listing`` (list)
            A list of strings that is the Doxygen xml <programlisting>, without the
            opening or closing <programlisting> tags.

        ``program_file`` (list)
            Managed externally by the root similar to ``file_name`` etc, this is the
            name of the file that will be created to display the program listing if it
            exists.  Set to ``None`` on creation, refer to
            :func:`exhale.ExhaleRoot.initializeNodeFilenameAndLink`.

        ``program_link_name`` (str)
            Managed externally by the root similar to ``file_name`` etc, this is the
            reStructuredText link that will be declared at the top of the
            ``program_file``. Set to ``None`` on creation, refer to
            :func:`exhale.ExhaleRoot.initializeNodeFilenameAndLink`.
    '''
    def __init__(self, name, kind, refid):
        self.name  = name
        self.kind  = kind
        self.refid = refid

        # used for establishing a link to the file something was done in for leaf-like
        # nodes conveniently, files also have this defined as their name making
        # comparison easy :)
        self.def_in_file = None

        ########## cdef_dict = self.openNodeCompoundDefDict()
        # if cdef_dict and "location" in cdef_dict and "@file" in cdef_dict["location"]:
        #     self.def_in_file = cdef_dict["location"]["@file"]

        # self.compound = breatheCompound
        # self.kind     = breatheCompound.get_kind()
        # self.name     = breatheCompound.get_name()
        # self.refid    = breatheCompound.get_refid()
        ##########
        self.children = []    # ExhaleNodes
        self.parent   = None  # if reparented, will be an ExhaleNode
        # managed externally
        self.file_name = None
        self.link_name = None
        self.title     = None
        # representation of hierarchies
        self.in_class_view = False
        self.in_directory_view = False
        # kind-specific additional information
        if self.kind == "file":
            self.namespaces_used   = []  # ExhaleNodes
            self.includes          = []  # strings
            self.included_by       = []  # (refid, name) tuples
            self.location          = ""
            self.program_listing   = []  # strings
            self.program_file      = ""
            self.program_link_name = ""

    def __lt__(self, other):
        '''
        The ``ExhaleRoot`` class stores a bunch of lists of ``ExhaleNode`` objects.
        When these lists are sorted, this method will be called to perform the sorting.

        :Parameters:
            ``other`` (ExhaleNode)
                The node we are comparing whether ``self`` is less than or not.

        :Return (bool):
            True if ``self`` is less than ``other``, False otherwise.
        '''
        # allows alphabetical sorting within types
        if self.kind == other.kind:
            return self.name.lower() < other.name.lower()
        # treat structs and classes as the same type
        elif self.kind == "struct" or self.kind == "class":
            if other.kind != "struct" and other.kind != "class":
                return True
            else:
                if self.kind == "struct" and other.kind == "class":
                    return True
                elif self.kind == "class" and other.kind == "struct":
                    return False
                else:
                    return self.name.lower() < other.name.lower()
        # otherwise, sort based off the kind
        else:
            return self.kind < other.kind

    def openNodeXMLAsDict(self):
        # Determine where the definition actually took place
        node_xml_path = "{}{}.xml".format(configs.doxygenOutputDirectory, self.refid)
        if os.path.isfile(node_xml_path):
            try:
                with open(node_xml_path, "r") as node_xml:
                    node_xml_contents = node_xml.read()

                node_xml_dict = xmltodict.parse(node_xml_contents, process_namespaces=True)
                return node_xml_dict

            except:
                return None

    def openNodeCompoundDefDict(self):
        root = self.openNodeXMLAsDict()
        if root and ("doxygen" in root and "compounddef" in root["doxygen"]):
            return root["doxygen"]["compounddef"]
        return root

    def findNestedNamespaces(self, lst):
        '''
        Recursive helper function for finding nested namespaces.  If this node is a
        namespace node, it is appended to ``lst``.  Each node also calls each of its
        child ``findNestedNamespaces`` with the same list.

        :Parameters:
            ``lst`` (list)
                The list each namespace node is to be appended to.
        '''
        if self.kind == "namespace":
            lst.append(self)
        for c in self.children:
            c.findNestedNamespaces(lst)

    def findNestedDirectories(self, lst):
        '''
        Recursive helper function for finding nested directories.  If this node is a
        directory node, it is appended to ``lst``.  Each node also calls each of its
        child ``findNestedDirectories`` with the same list.

        :Parameters:
            ``lst`` (list)
                The list each directory node is to be appended to.
        '''
        if self.kind == "dir":
            lst.append(self)
        for c in self.children:
            c.findNestedDirectories(lst)

    def findNestedClassLike(self, lst):
        '''
        Recursive helper function for finding nested classes and structs.  If this node
        is a class or struct, it is appended to ``lst``.  Each node also calls each of
        its child ``findNestedClassLike`` with the same list.

        :Parameters:
            ``lst`` (list)
                The list each class or struct node is to be appended to.
        '''
        if self.kind == "class" or self.kind == "struct":
            lst.append(self)
        for c in self.children:
            c.findNestedClassLike(lst)

    def findNestedEnums(self, lst):
        '''
        Recursive helper function for finding nested enums.  If this node is a class or
        struct it may have had an enum added to its child list.  When this occurred, the
        enum was removed from ``self.enums`` in the :class:`exhale.ExhaleRoot` class and
        needs to be rediscovered by calling this method on all of its children.  If this
        node is an enum, it is because a parent class or struct called this method, in
        which case it is added to ``lst``.

        **Note**: this is used slightly differently than nested directories, namespaces,
        and classes will be.  Refer to :func:`exhale.ExhaleRoot.generateNodeDocuments`
        function for details.

        :Parameters:
            ``lst`` (list)
                The list each enum is to be appended to.
        '''
        if self.kind == "enum":
            lst.append(self)
        for c in self.children:
            c.findNestedEnums(lst)

    def findNestedUnions(self, lst):
        '''
        Recursive helper function for finding nested unions.  If this node is a class or
        struct it may have had a union added to its child list.  When this occurred, the
        union was removed from ``self.unions`` in the :class:`exhale.ExhaleRoot` class
        and needs to be rediscovered by calling this method on all of its children.  If
        this node is a union, it is because a parent class or struct called this method,
        in which case it is added to ``lst``.

        **Note**: this is used slightly differently than nested directories, namespaces,
        and classes will be.  Refer to :func:`exhale.ExhaleRoot.generateNodeDocuments`
        function for details.

        :Parameters:
            ``lst`` (list)
                The list each union is to be appended to.
        '''
        if self.kind == "union":
            lst.append(self)
        for c in self.children:
            c.findNestedUnions(lst)

    def toConsole(self, level, printChildren=True):
        '''
        Debugging tool for printing hierarchies / ownership to the console.  Recursively
        calls children ``toConsole`` if this node is not a directory or a file, and
        ``printChildren == True``.

        :Parameters:
            ``level`` (int)
                The indentation level to be used, should be greater than or equal to 0.

            ``printChildren`` (bool)
                Whether or not the ``toConsole`` method for the children found in
                ``self.children`` should be called with ``level+1``.  Default is True,
                set to False for directories and files.
        '''
        indent = "  " * level
        print("{}- [{}]: {}".format(indent, self.kind, self.name))
        # files are children of directories, the file section will print those children
        if self.kind == "dir":
            for c in self.children:
                c.toConsole(level + 1, printChildren=False)
        elif printChildren:
            if self.kind == "file":
                print("{}[[[ location=\"{}\" ]]]".format("  " * (level + 1), self.location))
                for i in self.includes:
                    print("{}- #include <{}>".format("  " * (level + 1), i))
                for ref, name in self.included_by:
                    print("{}- included by: [{}]".format("  " * (level + 1), name))
                for n in self.namespaces_used:
                    n.toConsole(level + 1, printChildren=False)
                for c in self.children:
                    c.toConsole(level + 1)
            elif self.kind == "class" or self.kind == "struct":
                relevant_children = []
                for c in self.children:
                    if c.kind == "class" or c.kind == "struct" or \
                       c.kind == "enum"  or c.kind == "union":
                        relevant_children.append(c)

                for rc in sorted(relevant_children):
                    rc.toConsole(level + 1)
            elif self.kind != "union":
                for c in self.children:
                    c.toConsole(level + 1)

    def typeSort(self):
        '''
        Sorts ``self.children`` in place, and has each child sort its own children.
        Refer to :func:`exhale.ExhaleRoot.deepSortList` for more information on when
        this is necessary.
        '''
        self.children.sort()
        for c in self.children:
            c.typeSort()

    def inClassView(self):
        '''
        Whether or not this node should be included in the class view hierarchy.  Helper
        method for :func:`exhale.ExhaleNode.toClassView`.  Sets the member variable
        ``self.in_class_view`` to True if appropriate.

        :Return (bool):
            True if this node should be included in the class view --- either it is a
            node of kind ``struct``, ``class``, ``enum``, ``union``, or it is a
            ``namespace`` that one or more if its descendants was one of the previous
            four kinds.  Returns False otherwise.
        '''
        if self.kind == "namespace":
            for c in self.children:
                if c.inClassView():
                    return True
            return False
        else:
            # flag that this node is already in the class view so we can find the
            # missing top level nodes at the end
            self.in_class_view = True
            return self.kind == "struct" or self.kind == "class" or \
                   self.kind == "enum"   or self.kind == "union"  # noqa

    def toClassView(self, level, stream, treeView, lastChild=False):
        '''
        Recursively generates the class view hierarchy using this node and its children,
        if it is determined by :func:`exhale.ExhaleNode.inClassView` that this node
        should be included.

        :Parameters:
            ``level`` (int)
                An integer greater than or equal to 0 representing the indentation level
                for this node.

            ``stream`` (StringIO)
                The stream that is being written to by all of the nodes (created and
                destroyed by the ExhaleRoot object).

            ``treeView`` (bool)
                If False, standard reStructuredText bulleted lists will be written to
                the ``stream``.  If True, then raw html unordered lists will be written
                to the ``stream``.

            ``lastChild`` (bool)
                When ``treeView == True``, the unordered lists generated need to have
                an <li class="lastChild"> tag on the last child for the
                ``collapsibleList`` to work correctly.  The default value of this
                parameter is False, and should only ever be set to True internally by
                recursive calls to this method.
        '''
        has_nested_children = False
        if self.inClassView():
            if not treeView:
                stream.write("{}- :ref:`{}`\n".format('    ' * level, self.link_name))
            else:
                indent = '  ' * (level * 2)
                if lastChild:
                    opening_li = '<li class="lastChild">'
                else:
                    opening_li = '<li>'
                # turn double underscores into underscores, then underscores into hyphens
                html_link = self.link_name.replace("__", "_").replace("_", "-")
                # should always have at least two parts (templates will have more)
                title_as_link_parts = self.title.split(" ")
                qualifier = title_as_link_parts[0]
                link_title = " ".join(title_as_link_parts[1:])
                link_title = link_title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                html_link = '{} <a href="{}.html#{}">{}</a>'.format(qualifier,
                                                                    self.file_name.split('.rst')[0],
                                                                    html_link,
                                                                    link_title)
                # search for nested children to display as sub-items in the tree view
                if self.kind == "class" or self.kind == "struct":
                    nested_enums      = []
                    nested_unions     = []
                    nested_class_like = []
                    # important: only scan self.children, do not use recursive findNested* methods
                    for c in self.children:
                        if c.kind == "enum":
                            nested_enums.append(c)
                        elif c.kind == "union":
                            nested_unions.append(c)
                        elif c.kind == "struct" or c.kind == "class":
                            nested_class_like.append(c)

                    has_nested_children = nested_enums or nested_unions or nested_class_like  # <3 Python

                # if there are sub children, there needs to be a new html list generated
                if self.kind == "namespace" or has_nested_children:
                    next_indent = '  {}'.format(indent)
                    stream.write('{}{}\n{}{}\n{}<ul>\n'.format(indent, opening_li,
                                                               next_indent, html_link,
                                                               next_indent))
                else:
                    stream.write('{}{}{}</li>\n'.format(indent, opening_li, html_link))

            # include the relevant children (class like or nested namespaces / classes)
            if self.kind == "namespace":
                # pre-process and find everything that is relevant
                kids    = []
                nspaces = []
                for c in self.children:
                    if c.inClassView():
                        if c.kind == "namespace":
                            nspaces.append(c)
                        else:
                            kids.append(c)

                # always put nested namespaces last; parent dictates to the child if
                # they are the last child being printed
                kids.sort()
                num_kids = len(kids)

                nspaces.sort()
                num_nspaces = len(nspaces)

                last_child_index = num_kids + num_nspaces - 1
                child_idx = 0

                # first all of the nested namespaces, then the child class like
                for node in itertools.chain(nspaces, kids):
                    node.toClassView(level + 1, stream, treeView, child_idx == last_child_index)
                    child_idx += 1

                # now that all of the children haven been written, close the tags
                if treeView:
                    stream.write("  {}</ul>\n{}</li>\n".format(indent, indent))
            # current node is a class or struct with nested children
            elif has_nested_children:
                nested_class_like.sort()
                num_class_like = len(nested_class_like)

                nested_enums.sort()
                num_enums = len(nested_enums)

                nested_unions.sort()
                num_unions = len(nested_unions)

                last_child_index = num_class_like + num_enums + num_unions - 1
                child_idx = 0

                # first all of the classes / structs, then enums, then unions
                for node in itertools.chain(nested_class_like, nested_enums, nested_unions):
                    node.toClassView(level + 1, stream, treeView, child_idx == last_child_index)
                    child_idx += 1

                # now that all of the children haven been written, close the tags
                if treeView:
                    stream.write("  {}</ul>\n{}</li>\n".format(indent, indent))

    def inDirectoryView(self):
        '''
        Whether or not this node should be included in the file view hierarchy.  Helper
        method for :func:`exhale.ExhaleNode.toDirectoryView`.  Sets the member variable
        ``self.in_directory_view`` to True if appropriate.

        :Return (bool):
            True if this node should be included in the file view --- either it is a
            node of kind ``file``, or it is a ``dir`` that one or more if its
            descendants was a ``file``.  Returns False otherwise.
        '''
        if self.kind == "file":
            # flag that this file is already in the directory view so that potential
            # missing files can be found later.
            self.in_directory_view = True
            return True
        elif self.kind == "dir":
            for c in self.children:
                if c.inDirectoryView():
                    return True
        return False

    def toDirectoryView(self, level, stream, treeView, lastChild=False):
        '''
        Recursively generates the file view hierarchy using this node and its children,
        if it is determined by :func:`exhale.ExhaleNode.inDirectoryView` that this node
        should be included.

        :Parameters:
            ``level`` (int)
                An integer greater than or equal to 0 representing the indentation level
                for this node.

            ``stream`` (StringIO)
                The stream that is being written to by all of the nodes (created and
                destroyed by the ExhaleRoot object).

            ``treeView`` (bool)
                If False, standard reStructuredText bulleted lists will be written to
                the ``stream``.  If True, then raw html unordered lists will be written
                to the ``stream``.

            ``lastChild`` (bool)
                When ``treeView == True``, the unordered lists generated need to have
                an <li class="lastChild"> tag on the last child for the
                ``collapsibleList`` to work correctly.  The default value of this
                parameter is False, and should only ever be set to True internally by
                recursive calls to this method.
        '''
        if self.inDirectoryView():
            # pre-process and find everything that is relevant (need to know if there
            # are children or not before writing for the bootstrap side)
            if self.kind == "dir":
                dirs = []
                kids = []
                for c in self.children:
                    if c.inDirectoryView():
                        if c.kind == "dir":
                            dirs.append(c)
                        elif c.kind == "file":
                            kids.append(c)

                dirs.sort()
                num_dirs = len(dirs)

                kids.sort()
                num_kids = len(kids)

                total_kids = num_dirs + num_kids

                last_child_index = num_kids + num_dirs - 1
                child_idx = 0
            else:
                total_kids = 0

            if not treeView:
                stream.write("{}- :ref:`{}`\n".format('    ' * level, self.link_name))
            else:
                indent = '  ' * (level * 2)
                next_indent = "  {0}".format(indent)
                if configs.treeViewIsBootstrap:
                    stream.write("\n{indent}{{\n{next_indent}{text}".format(
                        indent=indent,
                        next_indent=next_indent,
                        text="text: \"{}\"".format(self.name))
                    )

                    # If there are children then `nodes: [ ... ]` will be next
                    if total_kids > 0:
                        stream.write(",")
                    # Otherwise, this element is ending.  JavaScript doesn't care about
                    # trailing commas :)
                    else:
                        stream.write("\n{indent}}},".format(indent=indent))
                else:
                    if lastChild:
                        opening_li = '<li class="lastChild">'
                    else:
                        opening_li = '<li>'
                    # turn double underscores into underscores, then underscores into hyphens
                    html_link = self.link_name.replace("__", "_").replace("_", "-")
                    # should always have at least two parts (templates will have more)
                    title_as_link_parts = self.title.split(" ")
                    qualifier = title_as_link_parts[0]
                    link_title = " ".join(title_as_link_parts[1:])
                    link_title = link_title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    html_link = '{} <a href="{}.html#{}">{}</a>'.format(qualifier,
                                                                        self.file_name.split('.rst')[0],
                                                                        html_link,
                                                                        link_title)
                    if self.kind == "dir":
                        next_indent = '  {}'.format(indent)
                        stream.write('{}{}\n{}{}\n{}<ul>\n'.format(indent, opening_li,
                                                                   next_indent, html_link,
                                                                   next_indent))
                    else:
                        stream.write('{}{}{}</li>\n'.format(indent, opening_li, html_link))

            # include the relevant children (class like or nested namespaces)
            if self.kind == "dir":
                if treeView and configs.treeViewIsBootstrap and (num_dirs + num_kids > 0):
                    stream.write("\n{next_indent}nodes: [\n".format(next_indent=next_indent))

                # first put in all of the nested directories
                for n in dirs:
                    n.toDirectoryView(level + 1, stream, treeView, child_idx == last_child_index)
                    child_idx += 1

                # then list all files in this directory
                for k in kids:
                    k.toDirectoryView(level + 1, stream, treeView, child_idx == last_child_index)
                    child_idx += 1

                # now that all of the children haven been written, close the tags
                if treeView:
                    if configs.treeViewIsBootstrap:
                        if num_dirs + num_kids > 0:
                            stream.write("\n{next_indent}]\n".format(next_indent=next_indent))
                        stream.write("\n{indent}}},\n".format(indent=indent))
                    else:
                        stream.write("  {}</ul>\n{}</li>\n".format(indent, indent))


class ExhaleRoot:
    '''
    The full representation of the hierarchy graphs.  In addition to containing specific
    lists of ExhaleNodes of interest, the ExhaleRoot class is responsible for comparing
    the parsed breathe hierarchy and rebuilding lost relationships using the Doxygen
    xml files.  Once the graph parsing has finished, the ExhaleRoot generates all of the
    relevant reStructuredText documents and links them together.

    The ExhaleRoot class is not designed for reuse at this time.  If you want to
    generate a new hierarchy with a different directory or something, changing all of
    the right fields may be difficult and / or unsuccessful.  Refer to the bottom of the
    source code for :func:`exhale.generate` for safe usage (just exception handling),
    but the design of this class is to be used as follows:

    .. code-block:: py

       textRoot = ExhaleRoot(... args ...)
       textRoot.parse()
       textRoot.generateFullAPI()

    Zero checks are in place to enforce this usage, and if you are modifying the
    execution of this class and things are not working make sure you follow the ordering
    of those methods.

    :Parameters:
        ``rootDirectory`` (str)
            The name of the root directory to put everything in.  This should be the
            value of the key ``containmentFolder`` in the dictionary passed to
            :func:`exhale.generate`.

        ``rootFileName`` (str)
            The name of the file the root library api will be put into.  This should not
            contain the ``rootDirectory`` path.  This should be the value of the key
            ``rootFileName`` in the dictionary passed to :func:`exhale.generate`.

        ``rootFileTitle`` (str)
            The title to be written to the top of ``rootFileName``.  This should be the
            value of the key ``rootFileTitle`` in the dictionary passed to
            :func:`exhale.generate`.

        ``rootFileDescription`` (str)
            The description of the library api file placed after ``rootFileTitle``.
            This should be the value of the key ``afterTitleDescription`` in the
            dictionary passed to :func:`exhale.generate`.

        ``rootFileSummary`` (str)
            The summary of the library api placed after the generated hierarchy views.
            This should be the value of the key ``afterBodySummary`` in the dictionary
            passed to :func:`exhale.generate`.

        ``createTreeView`` (bool)
            Creates the raw html unordered lists for use with ``collapsibleList`` if
            True.  Otherwise, creates standard reStructuredText bulleted lists.  Should
            be the value of the key ``createTreeView`` in the dictionary passed to
            :func:`exhale.generate`.

    :Attributes:
        ``root_directory`` (str)
            The value of the parameter ``rootDirectory``.

        ``root_file_name`` (str)
            The value of the parameter ``rootFileName``.

        ``full_root_file_path`` (str)
            The full file path of the root file (``"root_directory/root_file_name"``).

        ``root_file_title`` (str)
            The value of the parameter ``rootFileTitle``.

        ``root_file_description`` (str)
            The value of the parameter ``rootFileDescription``.

        ``root_file_summary`` (str)
            The value of the parameter ``rootFileSummary``.

        ``class_view_file`` (str)
            The full file path the class view hierarchy will be written to.  This is
            incorporated into ``root_file_name`` using an ``.. include:`` directive.

        ``directory_view_file`` (str)
            The full file path the file view hierarchy will be written to.  This is
            incorporated into ``root_file_name`` using an ``.. include:`` directive.

        ``unabridged_api_file`` (str)
            The full file path the full API will be written to.  This is incorporated
            into ``root_file_name`` using a ``.. toctree:`` directive with a
            ``:maxdepth:`` according to the value of the key ``fullToctreeMaxDepth``
            in the dictionary passed into :func:`exhale.generate`.

        ``use_tree_view`` (bool)
            The value of the parameter ``createTreeView``.

        ``all_compounds`` (list)
            A list of all the Breathe compound objects discovered along the way.
            Populated during :func:`exhale.ExhaleRoot.discoverAllNodes`.

        ``all_nodes`` (list)
            A list of all of the ExhaleNode objects created.  Populated during
            :func:`exhale.ExhaleRoot.discoverAllNodes`.

        ``node_by_refid`` (dict)
            A dictionary with string ExhaleNode ``refid`` values, and values that are the
            ExhaleNode it came from.  Storing it this way is convenient for when the
            Doxygen xml file is being parsed.

        ``class_like`` (list)
            The full list of ExhaleNodes of kind ``struct`` or ``class``

        ``defines`` (list)
            The full list of ExhaleNodes of kind ``define``.

        ``enums`` (list)
            The full list of ExhaleNodes of kind ``enum``.

        ``enum_values`` (list)
            The full list of ExhaleNodes of kind ``enumvalue``.  Populated, not used.

        ``functions`` (list)
            The full list of ExhaleNodes of kind ``function``.

        ``dirs`` (list)
            The full list of ExhaleNodes of kind ``dir``.

        ``files`` (list)
            The full list of ExhaleNodes of kind ``file``.

        ``groups`` (list)
            The full list of ExhaleNodes of kind ``group``.  Pupulated, not used.

        ``namespaces`` (list)
            The full list of ExhaleNodes of kind ``namespace``.

        ``typedefs`` (list)
            The full list of ExhaleNodes of kind ``typedef``.

        ``unions`` (list)
            The full list of ExhaleNodes of kind ``union``.

        ``variables`` (list)
            The full list of ExhaleNodes of kind ``variable``.
    '''
    # def __init__(self, breatheRoot, rootDirectory, rootFileName, rootFileTitle,
    #              rootFileDescription, rootFileSummary, createTreeView):
    def __init__(self):
        # file generation location and root index data
        self.root_directory        = configs.containmentFolder
        self.root_file_name        = configs.rootFileName
        self.full_root_file_path   = os.path.join(self.root_directory, self.root_file_name)
        self.root_file_title       = configs.rootFileTitle
        self.root_file_description = configs.afterTitleDescription
        self.root_file_summary     = configs.afterBodySummary
        self.class_view_file       = "{0}.rst".format(
            self.full_root_file_path.replace(self.root_file_name, "class_view_hierarchy")
        )
        self.directory_view_file   = "{0}.rst".format(
            self.full_root_file_path.replace(self.root_file_name, "directory_view_hierarchy")
        )
        self.unabridged_api_file   = "{0}.rst".format(
            self.full_root_file_path.replace(self.root_file_name, "unabridged_api")
        )

        # whether or not we should generate the raw html tree view
        self.use_tree_view = configs.createTreeView

        # track all compounds (from Breathe) to build all nodes (ExhaleNodes)
        # self.all_compounds = [self.breathe_root.get_compound()]
        self.all_compounds = []##### remove this
        self.all_nodes = []

        # convenience lookup: keys are string Doxygen refid's, values are ExhaleNodes
        self.node_by_refid = {}

        # breathe directive    breathe kind
        # -------------------+----------------+
        # autodoxygenfile  <-+-> IGNORE       |
        # doxygenindex     <-+-> IGNORE       |
        # autodoxygenindex <-+-> IGNORE       |
        # -------------------+----------------+
        # doxygenclass     <-+-> "class"      |
        # doxygenstruct    <-+-> "struct"     |
        self.class_like      = []           # |
        # doxygendefine    <-+-> "define"     |
        self.defines         = []           # |
        # doxygenenum      <-+-> "enum"       |
        self.enums           = []           # |
        # ---> largely ignored by framework,  |
        #      but stored if desired          |
        # doxygenenumvalue <-+-> "enumvalue"  |
        self.enum_values     = []           # |
        # doxygenfunction  <-+-> "function"   |
        self.functions       = []           # |
        # no directive     <-+-> "dir"        |
        self.dirs = []                      # |
        # doxygenfile      <-+-> "file"       |
        self.files           = []           # |
        # not used, but could be supported in |
        # the future?                         |
        # doxygengroup     <-+-> "group"      |
        self.groups          = []           # |
        # doxygennamespace <-+-> "namespace"  |
        self.namespaces      = []           # |
        # doxygentypedef   <-+-> "typedef"    |
        self.typedefs        = []           # |
        # doxygenunion     <-+-> "union"      |
        self.unions          = []           # |
        # doxygenvariable  <-+-> "variable"   |
        self.variables       = []           # |
        # -------------------+----------------+

    ####################################################################################
    #
    ##
    ### Parsing
    ##
    #
    ####################################################################################
    def parse(self):
        '''
        The first method that should be called after creating an ExhaleRoot object.  The
        Breathe graph is parsed first, followed by the Doxygen xml documents.  By the
        end of this method, all of the ``self.<breathe_kind>``, ``self.all_compounds``,
        and ``self.all_nodes`` lists as well as the ``self.node_by_refid`` dictionary
        will be populated.  Lastly, this method sorts all of the internal lists.  The
        order of execution is exactly

        1. :func:`exhale.ExhaleRoot.discoverAllNodes`
        2. :func:`exhale.ExhaleRoot.reparentAll`
        3. Populate ``self.node_by_refid`` using ``self.all_nodes``.
        4. :func:`exhale.ExhaleRoot.fileRefDiscovery`
        5. :func:`exhale.ExhaleRoot.filePostProcess`
        6. :func:`exhale.ExhaleRoot.sortInternals`
        '''
        # Find and reparent everything from the Breathe graph.
        self.discoverAllNodes()
        self.reparentAll()

        # now that we have all of the nodes, store them in a convenient manner for refid
        # lookup when parsing the Doxygen xml files
        for n in self.all_nodes:
            self.node_by_refid[n.refid] = n

        # find missing relationships using the Doxygen xml files
        self.fileRefDiscovery()
        self.filePostProcess()

        # sort all of the lists we just built
        self.sortInternals()

    def discoverAllNodes(self):
        '''
        Stack based traversal of breathe graph, creates some parental relationships
        between different ExhaleNode objects.  Upon termination, this method will have
        populated the lists ``self.all_compounds``, ``self.all_nodes``, and the
        ``self.<breathe_kind>`` lists for different types of objects.
        '''
        doxygen_index_xml = "{}/index.xml".format(configs.doxygenOutputDirectory)
        try:
            with open(doxygen_index_xml, "r") as index:
                index_contents = index.read()
        except:
            raise RuntimeError("Could not read the contents of [{}].".format(doxygen_index_xml))

        try:
            index_soup = BeautifulSoup(index_contents, "lxml-xml")
        except:
            raise RuntimeError("Could not parse the contents of [{}] as an xml.".format(doxygen_index_xml))

        doxygen_root = index_soup.doxygenindex
        if not doxygen_root:
            raise RuntimeError(
                "Did not find root XML node named 'doxygenindex' parsing [{}].".format(doxygen_index_xml)
            )

        for compound in doxygen_root.find_all("compound"):
            if compound.find("name") and "kind" in compound.attrs and "refid" in compound.attrs:
                curr_name  = compound.find("name").get_text()
                curr_kind  = compound.attrs["kind"]
                curr_refid = compound.attrs["refid"]
                curr_node  = ExhaleNode(curr_name, curr_kind, curr_refid)
                self.trackNodeIfUnseen(curr_node)

                # For things like files and namespaces, a "member" list will include
                # things like defines, enums, etc.  For classes and structs, we don't
                # need to pay attention because the members are the various methods or
                # data members by the class
                if curr_kind == "namespace" or curr_kind == "file":
                    for member in compound.find_all("member"):
                        if member.find("name") and "kind" in member.attrs and "refid" in member.attrs:
                            child_name  = member.find("name").get_text()
                            child_kind  = member.attrs["kind"]
                            child_refid = member.attrs["refid"]
                            child_node  = ExhaleNode(child_name, child_kind, child_refid)
                            self.trackNodeIfUnseen(child_node)

                            if curr_kind == "namespace":
                                child_node.parent = curr_node
                            else:  # curr_kind == "file"
                                child_node.def_in_file = curr_node

                            curr_node.children.append(child_node)
                # self.discoverNeighbors(compound, curr_node)

        # Now that we have discovered everything, we need to explicitly parse the file
        # xml documents to determine where leaf-like nodes have been declared.
        #
        # TODO: change formatting of namespace to provide a listing of all files using it
        for f in self.files:
            node_xml_contents = utils.nodeCompoundXMLContents(f)
            if node_xml_contents:
                try:
                    f.soup = BeautifulSoup(node_xml_contents, "lxml-xml")
                except Exception as e:
                    exclaimError("Unable to parse file xml [{0}]:\n{1}".format(f.name, e))
                    break

                try:
                    cdef = f.soup.doxygen.compounddef
                    err_non = "[CRITICAL] did not find refid [{0}] in `self.node_by_refid`."
                    err_dup = "Conflicting file definition: [{0}] appears to be defined in both [{1}] and [{2}]."
                    # process classes
                    inner_classes = cdef.find_all("innerclass", recursive=False)
                    exclaimError("*** [{}] had [{}] innerclass".format(f.name, len(inner_classes)), utils.AnsiColors.BOLD_MAGENTA)
                    for class_like in inner_classes:
                        if "refid" in class_like.attrs:
                            refid = class_like.attrs["refid"]
                            if refid in self.node_by_refid:
                                node = self.node_by_refid[refid]
                                exclaimError("   - [{}]".format(node.name), utils.AnsiColors.BOLD_MAGENTA)
                                if not node.def_in_file:
                                    node.def_in_file = f
                                elif node.def_in_file != f:
                                    exclaimError(err_dup.format(node.name, node.def_in_file.name, f.name),
                                                 utils.AnsiColors.BOLD_YELLOW)
                            else:
                                exclaimError(err_non.format(refid), utils.AnsiColors.BOLD_RED)
                        else:
                            ######### TODO: does this happen?
                            pass

                    # try and find anything else
                    memberdefs = cdef.find_all("memberdef", recursive=False)
                    exclaimError("*** [{}] had [{}] memberdef".format(f.name, len(memberdefs)), utils.AnsiColors.BOLD_MAGENTA)
                    for member in cdef.find_all("memberdef", recursive=False):
                        if "id" in member.attrs:
                            refid = member.attrs["id"]
                            if refid in self.node_by_refid:
                                node = self.node_by_refid[refid]
                                exclaimError("   - [{}]".format(node.name), utils.AnsiColors.BOLD_MAGENTA)
                                if not node.def_in_file:
                                    node.def_in_file = f

                    # the location of the file as determined by doxygen
                    location = cdef.find("location")
                    if location and "file" in location.attrs:
                        f.def_in_file_location = location.attrs["file"]
                    else:
                        f.def_in_file_location = None #######
                except Exception as e:
                    exclaimError("XXXXXXX ::: {} :: {}".format(f.name, e), utils.AnsiColors.BOLD_MAGENTA)

        ######
        # last chance: we will still miss some, but need to pause and establish namespace relationships
        for nspace in self.namespaces:
            node_xml_contents = utils.nodeCompoundXMLContents(nspace)
            if node_xml_contents:
                try:
                    name_soup = BeautifulSoup(node_xml_contents, "lxml-xml")
                except:
                    continue

                cdef = name_soup.doxygen.compounddef
                for class_like in cdef.find_all("innerclass", recursive=False):
                    if "refid" in class_like.attrs:
                        refid = class_like.attrs["refid"]
                        if refid in self.node_by_refid:
                            node = self.node_by_refid[refid]
                            if node not in nspace.children:
                                nspace.children.append(node)
                                node.parent = nspace

                for nested_nspace in cdef.find_all("innernamespace", recursive=False):
                    if "refid" in nested_nspace.attrs:
                        refid = nested_nspace.attrs["refid"]
                        if refid in self.node_by_refid:
                            node = self.node_by_refid[refid]
                            if node not in nspace.children:
                                nspace.children.append(node)
                                node.parent = nspace

                # This is where things get interesting
                for sectiondef in cdef.find_all("sectiondef", recursive=False):
                    for memberdef in sectiondef.find_all("memberdef", recursive=False):
                        if "id" in memberdef.attrs:
                            refid = memberdef.attrs["id"]
                            if refid in self.node_by_refid:
                                node = self.node_by_refid[refid]
                                location = memberdef.find("location")
                                if location:
                                    if "file" in location.attrs:
                                        filedef = location.attrs["file"]
                                        for f in self.files:
                                            if filedef == f.def_in_file_location:
                                                node.def_in_file = f
                                                if node not in f.children:
                                                    f.children.append(node)
                                                break



        missing_file_def = {}
        missing_file_def_candidates = {}
        for refid in self.node_by_refid:
            node = self.node_by_refid[refid]
            if node.def_in_file is None and node.kind not in ("file", "dir", "group", "namespace"):
                missing_file_def[refid] = node
                missing_file_def_candidates[refid] = []

        for f in self.files:
            cdef = f.soup.doxygen.compounddef
            # try and find things in the programlisting as a last resort
            programlisting = cdef.find("programlisting")
            if programlisting:
                for ref in programlisting.find_all("ref"):
                    if "refid" in ref.attrs:
                        refid = ref.attrs["refid"]
                        if "kindref" in ref.attrs and ref.attrs["kindref"] == "member":
                            if refid in missing_file_def and f not in missing_file_def_candidates[refid]:
                                missing_file_def_candidates[refid].append(f)
                        # elif "kindref" in ref.attrs:
                        # if "refkind" in ref.attrs:
                        #     exclaimError("=== refkind: {}".format(refid), utils.AnsiColors.BOLD_YELLOW)

        for refid in missing_file_def:
            node = missing_file_def[refid]
            candidates = missing_file_def_candidates[refid]
            # If only one found, life is good!
            if len(candidates) == 1:
                node.def_in_file = candidates[0]
            # elif len(candidates) > 1:
            #     import ipdb
            #     ipdb.set_trace()


        # When you call the breathe_root.get_compound() method, it returns a list of the
        # top level source nodes.  These start out on the stack, and we add their
        # children if they have not already been visited before.
        # nodes_remaining = [ExhaleNode(compound) for compound in self.breathe_root.get_compound()]
        # nodes_remaining = [ExhaleNode(compound) for compound in doxygen_root["compound"]]
        # while len(nodes_remaining) > 0:
        #     curr_node = nodes_remaining.pop()
        #     self.trackNodeIfUnseen(curr_node)
        #     self.discoverNeighbors(nodes_remaining, curr_node)

    def trackNodeIfUnseen(self, node):
        '''
        Helper method for :func:`exhale.ExhaleRoot.discoverAllNodes`.  If the node is
        not in self.all_nodes yet, add it to both self.all_nodes as well as the
        corresponding ``self.<breathe_kind>`` list.

        :Parameters:
            ``node`` (ExhaleNode)
                The node to begin tracking if not already present.
        '''
        if node not in self.all_nodes:
            self.all_nodes.append(node)
            self.node_by_refid[node.refid] = node
            if node.kind == "class" or node.kind == "struct":
                self.class_like.append(node)
            elif node.kind == "namespace":
                self.namespaces.append(node)
            elif node.kind == "enum":
                self.enums.append(node)
            elif node.kind == "enumvalue":
                self.enum_values.append(node)
            elif node.kind == "define":
                self.defines.append(node)
            elif node.kind == "file":
                self.files.append(node)
            elif node.kind == "dir":
                self.dirs.append(node)
            elif node.kind == "function":
                self.functions.append(node)
            elif node.kind == "variable":
                self.variables.append(node)
            elif node.kind == "group":
                self.groups.append(node)
            elif node.kind == "typedef":
                self.typedefs.append(node)
            elif node.kind == "union":
                self.unions.append(node)

    def discoverNeighbors(self, compoundTag, node):
        '''
        Helper method for :func:`exhale.ExhaleRoot.discoverAllNodes`.  Some of the
        compound objects received from Breathe have a member function ``get_member()``
        that returns all of the children.  Some do not.  This method checks to see if
        the method is present first, and if so performs the following::

            For every compound in node.compound.get_member():
                If compound not present in self.all_compounds:
                    - Add compound to self.all_compounds
                    - Create a child ExhaleNode
                    - If it is not a class, struct, or union, add to nodesRemaining
                    - If it is not an enumvalue, make it a child of node parameter

        :Parameters:
            ``nodesRemaining`` (list)
                The list of nodes representing the stack traversal being done by
                :func:`exhale.ExhaleRoot.discoverAllNodes`.  New neighbors found will
                be appended to this list.

            ``node`` (ExhaleNode)
                The node we are trying to discover potential new neighbors from.
        '''
        # discover neighbors of current node; some seem to not have get_member()
        # if "member" in node.compound.__dict__:
        if "member" in node.compound:
            for member in node.compound["member"]:
                # keep track of every compound we have seen
                if member not in self.all_compounds and \
                        ("name" in member and "@kind" in member and "@refid" in member):
                    self.all_compounds.append(member)
                    # if we haven't seen this compound yet, make a node
                    child_node = ExhaleNode(member)
                    # if the current node is a class, struct, union, or enum ignore
                    # its variables, functions, etc
                    if node.kind == "class" or node.kind == "struct" or node.kind == "union":
                        if child_node.kind == "enum" or child_node.kind == "union":
                            nodesRemaining.append(child_node)
                    elif node.kind == "file":
                        exclaimError("** [[[ {} ]]] {}".format(node.name, child_node.name), AnsiColors.BOLD_MAGENTA)
                    else:
                        nodesRemaining.append(child_node)
                    # the enum is presented separately, enumvals are haphazard and i hate them
                    # ... determining the enumvalue parent would be painful and i don't want to do it
                    if child_node.kind != "enumvalue":
                        node.children.append(child_node)
                        child_node.parent = node
                else:
                    exclaimError("$$ Already in all_compounds: [{}]".format(member), AnsiColors.BOLD_GREEN)

    def reparentAll(self):
        '''
        Fixes some of the parental relationships lost in parsing the Breathe graph.
        File relationships are recovered in :func:`exhale.ExhaleRoot.fileRefDiscovery`.
        This method simply calls in this order:

        1. :func:`exhale.ExhaleRoot.reparentUnions`
        2. :func:`exhale.ExhaleRoot.reparentClassLike`
        3. :func:`exhale.ExhaleRoot.reparentDirectories`
        4. :func:`exhale.ExhaleRoot.renameToNamespaceScopes`
        5. :func:`exhale.ExhaleRoot.reparentNamespaces`
        '''
        self.reparentUnions()
        self.reparentClassLike()
        self.reparentDirectories()
        self.renameToNamespaceScopes()
        self.reparentNamespaces()

        for node in self.all_nodes:
            node.children = list(set(node.children))

    def reparentUnions(self):
        '''
        Helper method for :func:`exhale.ExhaleRoot.reparentAll`.  Namespaces and classes
        should have the unions defined in them to be in the child list of itself rather
        than floating around.  Union nodes that are reparented (e.g. a union defined in
        a class) will be removed from the list ``self.unions`` since the Breathe
        directive for its parent (e.g. the class) will include the documentation for the
        union.  The consequence of this is that a union defined in a class will **not**
        appear in the full api listing of Unions.
        '''
        # unions declared in a class will not link to the individual union page, so
        # we will instead elect to remove these from the list of unions
        removals = []
        for u in self.unions:
            parts = u.name.split("::")
            num_parts = len(parts)
            if num_parts > 1:
                # it can either be a child of a namespace or a class_like
                if num_parts > 2:
                    namespace_name  = "::".join(p for p in parts[:-2])
                    potential_class = parts[-2]

                    # see if it belongs to a class like object first. if so, remove this
                    # union from the list of unions
                    reparented = False
                    for cl in self.class_like:
                        if cl.name == potential_class:
                            cl.children.append(u)
                            u.parent = cl
                            reparented = True
                            break

                    if reparented:
                        removals.append(u)
                        continue

                    # otherwise, see if it belongs to a namespace
                    alt_namespace_name = "{}::{}".format(namespace_name, potential_class)
                    for n in self.namespaces:
                        if namespace_name == n.name or alt_namespace_name == n.name:
                            n.children.append(u)
                            u.parent = n
                            break
                else:
                    name_or_class_name = "::".join(p for p in parts[:-1])

                    # see if it belongs to a class like object first. if so, remove this
                    # union from the list of unions
                    reparented = False
                    for cl in self.class_like:
                        if cl.name == name_or_class_name:
                            cl.children.append(u)
                            u.parent = cl
                            reparented = True
                            break

                    if reparented:
                        removals.append(u)
                        continue

                    # next see if it belongs to a namespace
                    for n in self.namespaces:
                        if n.name == name_or_class_name:
                            n.children.append(u)
                            u.parent = n
                            break

        # remove the unions from self.unions that were declared in class_like objects
        for rm in removals:
            self.unions.remove(rm)

    def reparentClassLike(self):
        '''
        Helper method for :func:`exhale.ExhaleRoot.reparentAll`.  Iterates over the
        ``self.class_like`` list and adds each object as a child to a namespace if the
        class, or struct is a member of that namespace.  Many classes / structs will be
        reparented to a namespace node, these will remain in ``self.class_like``.
        However, if a class or struct is reparented to a different class or struct (it
        is a nested class / struct), it *will* be removed from so that the class view
        hierarchy is generated correctly.
        '''
        removals = []
        # for cl in self.class_like:
        #     parts = cl.name.split("::")
        #     if len(parts) > 1:
        #         # first try and reparent to namespaces
        #         namespace_name = "::".join(parts[:-1])
        #         parent_found = False
        #         for n in self.namespaces:
        #             if n.name == namespace_name:
        #                 n.children.append(cl)
        #                 cl.parent = n
        #                 parent_found = True
        #                 break

        #         # if a namespace parent wasn not found, try and reparent to a class
        #         if not parent_found:
        #             # parent class name would be namespace_name
        #             for p_cls in self.class_like:
        #                 if p_cls.name == namespace_name:
        #                     p_cls.children.append(cl)
        #                     cl.parent = p_cls
        #                     removals.append(cl)
        #                     break
        for cl in self.class_like:
            parts = cl.name.split("::")
            if len(parts) > 1:
                parent_name = "::".join(parts[:-1])
                for parent_cl in self.class_like:
                    if parent_cl.name == parent_name:
                        parent_cl.children.append(cl)
                        cl.parent = parent_cl
                        removals.append(cl)
                        break

        for rm in removals:
            if rm in self.class_like:
                self.class_like.remove(rm)

    def reparentDirectories(self):
        '''
        Helper method for :func:`exhale.ExhaleRoot.reparentAll`.  Adds subdirectories as
        children to the relevant directory ExhaleNode.  If a node in ``self.dirs`` is
        added as a child to a different directory node, it is removed from the
        ``self.dirs`` list.
        '''
        dir_parts = []
        dir_ranks = []
        for d in self.dirs:
            parts = d.name.split("/")
            for p in parts:
                if p not in dir_parts:
                    dir_parts.append(p)
            dir_ranks.append((len(parts), d))

        traversal = sorted(dir_ranks)
        removals = []
        for rank, directory in reversed(traversal):
            # rank one means top level directory
            if rank < 2:
                break
            # otherwise, this is nested
            for p_rank, p_directory in reversed(traversal):
                if p_rank == rank - 1:
                    if p_directory.name == "/".join(directory.name.split("/")[:-1]):
                        p_directory.children.append(directory)
                        directory.parent = p_directory
                        if directory not in removals:
                            removals.append(directory)
                        break

        for rm in removals:
            self.dirs.remove(rm)

    def renameToNamespaceScopes(self):
        '''
        Helper method for :func:`exhale.ExhaleRoot.reparentAll`.  Some compounds in
        Breathe such as functions and variables do not have the namespace name they are
        declared in before the name of the actual compound.  This method prepends the
        appropriate (nested) namespace name before the name of any child that does not
        already have it.

        For example, the variable ``MAX_DEPTH`` declared in namespace ``external`` would
        have its ExhaleNode's ``name`` attribute changed from ``MAX_DEPTH`` to
        ``external::MAX_DEPTH``.
        '''
        for n in self.namespaces:
            namespace_name = "{}::".format(n.name)
            for child in n.children:
                if namespace_name not in child.name:
                    child.name = "{}{}".format(namespace_name, child.name)

    def reparentNamespaces(self):
        '''
        Helper method for :func:`exhale.ExhaleRoot.reparentAll`.  Adds nested namespaces
        as children to the relevant namespace ExhaleNode.  If a node in
        ``self.namespaces`` is added as a child to a different namespace node, it is
        removed from the ``self.namespaces`` list.  Because these are removed from
        ``self.namespaces``, it is important that
        :func:`exhale.ExhaleRoot.renameToNamespaceScopes` is called before this method.
        '''
        # namespace_parts = []
        # namespace_ranks = []
        # for n in self.namespaces:
        #     parts = n.name.split("::")
        #     for p in parts:
        #         if p not in namespace_parts:
        #             namespace_parts.append(p)
        #     namespace_ranks.append((len(parts), n))

        # traversal = sorted(namespace_ranks)
        # removals = []
        # for rank, namespace in reversed(traversal):
        #     # rank one means top level namespace
        #     if rank < 2:
        #         continue
        #     # otherwise, this is nested
        #     for p_rank, p_namespace in reversed(traversal):
        #         if p_rank == rank - 1:
        #             if p_namespace.name == "::".join(namespace.name.split("::")[:-1]):
        #                 p_namespace.children.append(namespace)
        #                 namespace.parent = p_namespace
        #                 if namespace not in removals:
        #                     removals.append(namespace)
                        # continue

        removals = []
        for nspace in self.namespaces:
            if nspace.parent and nspace.parent.kind == "namespace" and nspace not in removals:
                removals.append(nspace)

        for rm in removals:
            self.namespaces.remove(rm)

    def fileRefDiscovery(self):
        '''
        Finds the missing components for file nodes by parsing the Doxygen xml (which is
        just the ``doxygen_output_dir/node.refid``).  Additional items parsed include
        adding items whose ``refid`` tag are used in this file, the <programlisting> for
        the file, what it includes and what includes it, as well as the location of the
        file (with respsect to the *Doxygen* root).

        Care must be taken to only include a refid found with specific tags.  The
        parsing of the xml file was done by just looking at some example outputs.  It
        seems to be working correctly, but there may be some subtle use cases that break
        it.

        .. warning::
            Some enums, classes, variables, etc declared in the file will not have their
            associated refid in the declaration of the file, but will be present in the
            <programlisting>.  These are added to the files' list of children when they
            are found, but this parental relationship cannot be formed if you set
            ``XML_PROGRAMLISTING = NO`` with Doxygen.  An example of such an enum would
            be an enum declared inside of a namespace within this file.
        '''
        if not os.path.isdir(configs.doxygenOutputDirectory):
            exclaimError("The doxygen xml output directory [{}] is not valid!".format(
                configs.doxygenOutputDirectory
            ))
            return

        # parse the doxygen xml file and extract all refid's put in it
        # keys: file object, values: list of refid's
        doxygen_xml_file_ownerships = {}
        # innerclass, innernamespace, etc
        ref_regex    = re.compile(r'.*<inner.*refid="(\w+)".*')
        # what files this file includes
        inc_regex    = re.compile(r'.*<includes.*>(.+)</includes>')
        # what files include this file
        inc_by_regex = re.compile(r'.*<includedby refid="(\w+)".*>(.*)</includedby>')
        # the actual location of the file
        loc_regex    = re.compile(r'.*<location file="(.*)"/>')

        for f in self.files:
            # if f.name == "camera_state.hpp":
            #     import ipdb
            #     ipdb.set_trace()


            doxygen_xml_file_ownerships[f] = []
            try:
                doxy_xml_path = os.path.join(configs.doxygenOutputDirectory, "{0}.xml".format(f.refid))
                with open(doxy_xml_path, "r") as doxy_file:
                    processing_code_listing = False  # shows up at bottom of xml
                    for line in doxy_file:
                        # see if this line represents the location tag
                        match = loc_regex.match(line)
                        if match is not None:
                            f.location = match.groups()[0]
                            continue

                        if not processing_code_listing:
                            # gather included by references
                            match = inc_by_regex.match(line)
                            if match is not None:
                                ref, name = match.groups()
                                f.included_by.append((ref, name))
                                continue
                            # gather includes lines
                            match = inc_regex.match(line)
                            if match is not None:
                                inc = match.groups()[0]
                                f.includes.append(inc)
                                continue
                            # gather any classes, namespaces, etc declared in the file
                            match = ref_regex.match(line)
                            if match is not None:
                                match_refid = match.groups()[0]
                                if match_refid in self.node_by_refid:
                                    doxygen_xml_file_ownerships[f].append(match_refid)
                                continue
                            # lastly, see if we are starting the code listing
                            if "<programlisting>" in line:
                                processing_code_listing = True
                        elif processing_code_listing:
                            if "</programlisting>" in line:
                                processing_code_listing = False
                            else:
                                f.program_listing.append(line)
            except:
                exclaimError("Unable to process doxygen xml for file [{}].\n".format(f.name))

        #
        # IMPORTANT: do not set the parent field of anything being added as a child to the file
        #

        # hack to make things work right on RTD
        if configs.doxygenStripFromPath is not None:
            for f in self.files:
                # Strip out the path provided to Doxygen
                f.location = f.location.replace(configs.doxygenStripFromPath, "")
                # Remove leading path separator; the above line typically turns
                # something like:
                #
                #     /some/long/absolute/path/include/dir/file.hpp
                #
                # into
                #
                #    /dir/file.hpp
                #
                # so we want to make sure to remove the leading / in this case.
                if f.location.startswith(os.sep):
                    f.location = f.location(os.sep, "", 1)

        # now that we have parsed all the listed refid's in the doxygen xml, reparent
        # the nodes that we care about
        for f in self.files:
            for match_refid in doxygen_xml_file_ownerships[f]:
                child = self.node_by_refid[match_refid]
                if child.kind == "struct" or child.kind == "class" or child.kind == "function" or \
                   child.kind == "typedef" or child.kind == "define" or child.kind == "enum"   or \
                   child.kind == "union":
                    already_there = False
                    for fc in f.children:
                        if child.name == fc.name:
                            already_there = True
                            break
                    if not already_there:
                        # special treatment for unions: ignore if it is a class union
                        if child.kind == "union":
                            for u in self.unions:
                                if child.name == u.name:
                                    f.children.append(child)
                                    break
                        else:
                            f.children.append(child)
                elif child.kind == "namespace":
                    already_there = False
                    for fc in f.namespaces_used:
                        if child.name == fc.name:
                            already_there = True
                            break
                    if not already_there:
                        f.namespaces_used.append(child)

        # last but not least, some different kinds declared in the file that are scoped
        # in a namespace they will show up in the programlisting, but not at the toplevel.
        for f in self.files:
            potential_orphans = []
            for n in f.namespaces_used:
                for child in n.children:
                    if child.kind == "enum"     or child.kind == "variable" or \
                       child.kind == "function" or child.kind == "typedef"  or \
                       child.kind == "union":
                        potential_orphans.append(child)

            # now that we have a list of potential orphans, see if this doxygen xml had
            # the refid of a given child present.
            for orphan in potential_orphans:
                unresolved_name = orphan.name.split("::")[-1]
                if f.refid in orphan.refid and any(unresolved_name in line for line in f.program_listing):
                    if orphan not in f.children:
                        f.children.append(orphan)

        # Last but not least, make sure all children know where they were defined.
        for f in self.files:
            for child in f.children:
                if child.def_in_file is None:
                    child.def_in_file = f
                elif child.def_in_file != f:
                    exclaimError(
                        "Conflicting file definition for [{0}]: both [{1}] and [{2}] found.".format(
                            child.name, child.def_in_file.name, f.name
                        ),
                        utils.AnsiColors.BOLD_RED
                    )

    def filePostProcess(self):
        '''
        The real name of this method should be ``reparentFiles``, but to avoid confusion
        with what stage this must happen at it is called this instead.  After the
        :func:`exhale.ExhaleRoot.fileRefDiscovery` method has been called, each file
        will have its location parsed.  This method reparents files to directories
        accordingly, so the file view hierarchy can be complete.
        '''
        for f in self.files:
            dir_loc_parts = f.location.split("/")[:-1]
            num_parts = len(dir_loc_parts)
            # nothing to do, at the top level
            if num_parts == 0:
                continue

            dir_path = "/".join(p for p in dir_loc_parts)
            nodes_remaining = [d for d in self.dirs]
            while len(nodes_remaining) > 0:
                d = nodes_remaining.pop()
                if d.name in dir_path:
                    # we have found the directory we want
                    if d.name == dir_path:
                        d.children.append(f)
                        f.parent = d
                        break
                    # otherwise, try and find an owner
                    else:
                        nodes_remaining = []
                        for child in d.children:
                            if child.kind == "dir":
                                nodes_remaining.append(child)

    def sortInternals(self):
        '''
        Sort all internal lists (``class_like``, ``namespaces``, ``variables``, etc)
        mostly how doxygen would, alphabetical but also hierarchical (e.g. structs
        appear before classes in listings).  Some internal lists are just sorted, and
        some are deep sorted (:func:`exhale.ExhaleRoot.deepSortList`).
        '''
        # some of the lists only need to be sorted, some of them need to be sorted and
        # have each node sort its children
        # leaf-like lists: no child sort
        self.defines.sort()
        self.enums.sort()
        self.enum_values.sort()
        self.functions.sort()
        self.groups.sort()
        self.typedefs.sort()
        self.variables.sort()

        # hierarchical lists: sort children
        self.deepSortList(self.class_like)
        self.deepSortList(self.namespaces)
        self.deepSortList(self.unions)
        self.deepSortList(self.files)
        self.deepSortList(self.dirs)

    def deepSortList(self, lst):
        '''
        For hierarchical internal lists such as ``namespaces``, we want to sort both the
        list as well as have each child sort its children by calling
        :func:`exhale.ExhaleNode.typeSort`.

        :Parameters:
            ``lst`` (list)
                The list of ExhaleNode objects to be deep sorted.
        '''
        lst.sort()
        for l in lst:
            l.typeSort()

    ####################################################################################
    #
    ##
    ### Library generation.
    ##
    #
    ####################################################################################
    def generateFullAPI(self):
        '''
        Since we are not going to use some of the breathe directives (e.g. namespace or
        file), when representing the different views of the generated API we will need:

        1. Generate a single file restructured text document for all of the nodes that
           have either no children, or children that are leaf nodes.
        2. When building the view hierarchies (class view and file view), provide a link
           to the appropriate files generated previously.

        If adding onto the framework to say add another view (from future import groups)
        you would link from a restructured text document to one of the individually
        generated files using the value of ``link_name`` for a given ExhaleNode object.

        This method calls in this order:

        1. :func:`exhale.ExhaleRoot.generateAPIRootHeader`
        2. :func:`exhale.ExhaleRoot.generateNodeDocuments`
        3. :func:`exhale.ExhaleRoot.generateAPIRootBody`
        4. :func:`exhale.ExhaleRoot.generateAPIRootSummary`
        '''
        self.generateAPIRootHeader()
        self.generateNodeDocuments()
        self.generateAPIRootBody()
        self.generateAPIRootSummary()

    def generateAPIRootHeader(self):
        '''
        This method creates the root library api file that will include all of the
        different hierarchy views and full api listing.  If ``self.root_directory`` is
        not a current directory, it is created first.  Afterward, the root API file is
        created and its title is written, as well as the value of
        ``self.root_file_description``.
        '''
        try:
            if not os.path.isdir(self.root_directory):
                os.mkdir(self.root_directory)
        except Exception as e:
            exclaimError("Cannot create the directory: {}\nError message: {}".format(self.root_directory, e))
            raise Exception("Fatal error generating the api root, cannot continue.")
        try:
            with open(self.full_root_file_path, "w") as generated_index:
                generated_index.write("{}\n{}\n\n{}\n\n".format(
                    self.root_file_title, configs.SECTION_HEADING, self.root_file_description)
                )
        except:
            exclaimError("Unable to create the root api file / header: {}".format(self.full_root_file_path))
            raise Exception("Fatal error generating the api root, cannot continue.")

    def generateNodeDocuments(self):
        '''
        Creates all of the reStructuredText documents related to types parsed by
        Doxygen.  This includes all leaf-like documents (``class``, ``struct``,
        ``enum``, ``typedef``, ``union``, ``variable``, and ``define``), as well as
        namespace, file, and directory pages.

        During the reparenting phase of the parsing process, nested items were added as
        a child to their actual parent.  For classes, structs, enums, and unions, if
        it was reparented to a ``namespace`` it will *remain* in its respective
        ``self.<breathe_kind>`` list.  However, if it was an internally declared child
        of a class or struct (nested classes, structs, enums, and unions), this node
        will be removed from its ``self.<breathe_kind>`` list to avoid duplication in
        the class hierarchy generation.

        When generating the full API, though, we will want to include all of these and
        therefore must call :func:`exhale.ExhaleRoot.generateSingleNodeRST` with all of
        the nested items.  For nested classes and structs, this is done by just calling
        ``node.findNestedClassLike`` for every node in ``self.class_like``.  The
        resulting list then has all of ``self.class_like``, as well as any nested
        classes and structs found.  With ``enum`` and ``union``, these would have been
        reparented to a **class** or **struct** if it was removed from the relevant
        ``self.<breathe_kind>`` list.  Meaning we must make sure that we genererate the
        single node RST documents for everything by finding the nested enums and unions
        from ``self.class_like``, as well as everything in ``self.enums`` and
        ``self.unions``.
        '''
        # initialize all of the nodes
        for node in self.all_nodes:
            self.initializeNodeFilenameAndLink(node)

        # find the potentially nested items that were reparented
        nested_enums      = []
        nested_unions     = []
        nested_class_like = []
        for cl in self.class_like:
            cl.findNestedEnums(nested_enums)
            cl.findNestedUnions(nested_unions)
            cl.findNestedClassLike(nested_class_like)

        # generate all of the leaf-like documents
        for node in itertools.chain(nested_class_like, self.enums, nested_enums,
                                    self.unions, nested_unions, self.functions,
                                    self.typedefs, self.variables, self.defines):
            self.generateSingleNodeRST(node)

        # generate the remaining parent-like documents
        self.generateNamespaceNodeDocuments()
        self.generateFileNodeDocuments()
        self.generateDirectoryNodeDocuments()

    def initializeNodeFilenameAndLink(self, node):
        '''
        Sets the ``file_name`` and ``link_name`` for the specified node.  If the kind
        of this node is "file", then this method will also set the ``program_file``
        as well as the ``program_link_name`` fields.

        Since we are operating inside of a ``containmentFolder``, this method **will**
        include ``self.root_directory`` in this path so that you can just use::

            with open(node.file_name, "w") as gen_file:
                ... write the file ...

        Having the ``containmentFolder`` is important for when we want to generate the
        file, but when we want to use it with ``include`` or ``toctree`` this will
        need to change.  Refer to :func:`exhale.ExhaleRoot.gerrymanderNodeFilenames`.

        This method also sets the value of ``node.title``, which will be used in both
        the reStructuredText document of the node as well as the links generated in the
        class view hierarchy (<a href="..."> for the ``createTreeView = True`` option).

        :type:  exhale.ExhaleNode
        :param: node
            The node that we are setting the above information for.
        '''
        # create the file and link names
        html_safe_name = node.name.replace(":", "_").replace("/", "_")
        node.file_name = "{}/exhale_{}_{}.rst".format(self.root_directory, node.kind, html_safe_name)
        node.link_name = "{}_{}".format(qualifyKind(node.kind).lower(), html_safe_name)
        if node.kind == "file":
            # account for same file name in different directory
            html_safe_name = node.location.replace("/", "_")
            node.file_name = "{}/exhale_{}_{}.rst".format(self.root_directory, node.kind, html_safe_name)
            node.link_name = "{}_{}".format(qualifyKind(node.kind).lower(), html_safe_name)
            node.program_file = "{}/exhale_program_listing_file_{}.rst".format(
                self.root_directory, html_safe_name
            )
            node.program_link_name = "program_listing_file_{}".format(html_safe_name)

        # create the title for this node.
        if node.kind == "dir":
            title = node.name.split("/")[-1]
        # breathe does not prepend the namespace for variables and typedefs, so
        # I choose to leave the fully qualified name in the title for added clarity
        elif node.kind == "variable" or node.kind == "typedef":
            title = node.name
        else:
            #
            # :TODO: This is probably breaking template specializations, need to redo
            #        the html_safe_name, file_name, and link_name to account for these
            #        as well as include documentation for how to link to partial
            #        template specializations.
            #
            #        That is, need to do something like
            #
            #        html_safe_name = node.name.replace(":", "_")
            #                                  .replace("/", "_")
            #                                  .replace(" ", "_")
            #                                  .replace("<", "LT_")
            #                                  .replace(">", "_GT")
            #
            #        Or something like that...
            #
            first_lt = node.name.find("<")
            last_gt  = node.name.rfind(">")
            # dealing with a template, special treatment necessary
            if first_lt > -1 and last_gt > -1:
                title = "{}{}".format(
                    node.name[:first_lt].split("::")[-1],  # remove namespaces
                    node.name[first_lt:last_gt + 1]        # template params
                )
                html_safe_name = title.replace(":", "_").replace("/", "_").replace(" ", "_").replace("<", "LT_").replace(">", "_GT").replace(",", "")
                node.file_name = "{}/exhale_{}_{}.rst".format(self.root_directory, node.kind, html_safe_name)
                node.link_name = "{}_{}".format(qualifyKind(node.kind).lower(), html_safe_name)
                if node.kind == "file":
                    node.program_file = "{}/exhale_program_listing_file_{}.rst".format(
                        self.root_directory, html_safe_name
                    )
                    node.program_link_name = "program_listing_file_{}".format(html_safe_name)
            else:
                title = node.name.split("::")[-1]

            # additionally, I feel that nested classes should have their fully qualified
            # name without namespaces for clarity
            prepend_parent = False
            if node.kind == "class" or node.kind == "struct" or node.kind == "enum" or node.kind == "union":
                if node.parent is not None and (node.parent.kind == "class" or node.parent.kind == "struct"):
                    prepend_parent = True
            if prepend_parent:
                title = "{}::{}".format(node.parent.name.split("::")[-1], title)
        node.title = "{} {}".format(qualifyKind(node.kind), title)

    def generateSingleNodeRST(self, node):
        '''
        Creates the reStructuredText document for the leaf like node object.  This
        method should only be used with nodes in the following member lists:

        - ``self.class_like``
        - ``self.enums``
        - ``self.functions``
        - ``self.typedefs``
        - ``self.unions``
        - ``self.variables``
        - ``self.defines``

        File, directory, and namespace nodes are treated separately.

        :Parameters:
            ``node`` (ExhaleNode)
                The leaf like node being generated by this method.
        '''
        try:
            with open(node.file_name, "w") as gen_file:
                # generate a link label for every generated file
                link_declaration = ".. _{}:".format(node.link_name)

                # acquire the file this was originally defined in
                if node.def_in_file:
                    defined_in = "- Defined in :ref:`{where}`".format(where=node.def_in_file.link_name)
                else:
                    defined_in = ".. did not find file this was defined in"
                    exclaimError(
                        "Did not locate the file that defined {} [{}]; no link generated.".format(node.kind,
                                                                                                  node.name)
                    )

                # link to outer types if this node is a nested type
                if node.parent and (node.parent.kind == "struct" or node.parent.kind == "class"):
                    nested_type_of = "- Nested type of :ref:`{parent}`".format(parent=node.parent.link_name)
                else:
                    nested_type_of = ".. this is not a nested type"
                # link back to the file this was defined in
                file_included = False
                # same error can be thrown twice in below code segment
                multi_parent = "Critical error: this node is parented to multiple files.\n\nNode: {}"
                # for f in self.files:
                #     if node in f.children:
                #         if file_included:
                #             raise RuntimeError(multi_parent.format(node.name))
                #         header = "{}- Defined in :ref:`{}`\n\n".format(header, f.link_name)
                #         file_included = True
                # if this is a nested type, link back to its parent
                ####################################3
                # if node.parent is not None and (node.parent.kind == "struct" or node.parent.kind == "class"):
                #     # still a chance to recover if the parent worked. probably doesn't work past one layer
                #     # TODO: create like quadruple nested classes and find a way to reverse upward. parent links
                #     #       should just be class or struct until it is a namespace or file?
                #     if not file_included:
                #         parent_traverser = node.parent
                #         while parent_traverser is not None:
                #             for f in self.files:
                #                 if node.parent in f.children:
                #                     if file_included:
                #                         raise RuntimeError(multi_parent.format(node.name))
                #                     header = "{}- Defined in :ref:`{}`\n\n".format(header, f.link_name)
                #                     file_included = True
                #                     if node not in f.children:
                #                         f.children.append(node)
                #             if file_included:
                #                 parent_traverser = None
                #             else:
                #                 parent_traverser = parent_traverser.parent

                #     header = "{}- Nested type of :ref:`{}`\n\n".format(header, node.parent.link_name)
                ################################
                # if this has nested types, link to them
                nested_defs = ".. no nested types to include"
                if node.kind == "class" or node.kind == "struct":
                    nested_children = []
                    for c in node.children:
                        c.findNestedEnums(nested_children)
                        c.findNestedUnions(nested_children)
                        c.findNestedClassLike(nested_children)

                    if nested_children:
                        # build up a list of links, custom sort function will force
                        # double nested and beyond to appear after their parent by
                        # sorting on their name
                        nested_children.sort(key=lambda x: x.name)
                        nested_child_stream = StringIO()
                        for nc in nested_children:
                            nested_child_stream.write("- :ref:`{}`\n".format(nc.link_name))

                        # extract the list of links and add them as a subsection in the header
                        nested_child_string = nested_child_stream.getvalue()
                        nested_child_stream.close()
                        nested_defs = textwrap.dedent('''
                            **Nested Types**:

                            {children}
                        '''.format(children=nested_child_string))
                # inject the appropriate doxygen directive and name of this node
                directive = ".. {directive}:: {name}".format(
                    directive=kindAsBreatheDirective(node.kind),
                    name=node.name
                )
                # include any specific directives for this doxygen directive
                specifications = "{}".format(specificationsForKind(node.kind))
                gen_file.write(textwrap.dedent('''\
                    :tocdepth: {page_depth}

                    {link}

                    {heading}
                    {heading_mark}

                    {defined_in}

                    {nested_type_of}
                '''.format(
                    page_depth=configs.exhaleApiPageTocDepth,
                    link=link_declaration,
                    heading=node.title,
                    heading_mark=configs.SECTION_HEADING,
                    defined_in=defined_in,
                    nested_type_of=nested_type_of
                )))
                if nested_defs:
                    gen_file.write(nested_defs)
                gen_file.write(textwrap.dedent('''
                    {directive}
                '''.format(
                    nested_defs=nested_defs,
                    directive=directive,
                )))
                gen_file.write(specifications)
        except Exception as e:
            exclaimError("Critical error while generating the file for [{}]:\n{}".format(node.file_name, e))

    def generateNamespaceNodeDocuments(self):
        '''
        Generates the reStructuredText document for every namespace, including nested
        namespaces that were removed from ``self.namespaces`` (but added as children
        to one of the namespaces in ``self.namespaces``).

        The documents generated do not use the Breathe namespace directive, but instead
        link to the relevant documents associated with this namespace.
        '''
        # go through all of the top level namespaces
        for n in self.namespaces:
            # find any nested namespaces
            nested_namespaces = []
            for child in n.children:
                child.findNestedNamespaces(nested_namespaces)
            # generate the children first
            for nested in reversed(sorted(nested_namespaces)):
                self.generateSingleNamespace(nested)
            # generate this top level namespace
            self.generateSingleNamespace(n)

    def generateSingleNamespace(self, nspace):
        '''
        Helper method for :func:`exhale.ExhaleRoot.generateNamespaceNodeDocuments`.
        Writes the reStructuredText file for the given namespace.

        :Parameters:
            ``nspace`` (ExhaleNode)
                The namespace node to create the reStructuredText document for.
        '''
        try:
            ######TODO page_depth, textwrapdedent
            with open(nspace.file_name, "w") as gen_file:
                # generate a link label for every generated file
                link_declaration = ".. _{}:\n\n".format(nspace.link_name)
                # every generated file must have a header for sphinx to be happy
                nspace.title = "{} {}".format(qualifyKind(nspace.kind), nspace.name)
                header = "{}\n{}\n\n".format(nspace.title, configs.SECTION_HEADING)
                # generate the headings and links for the children
                children_string = self.generateNamespaceChildrenString(nspace)
                # write it all out
                gen_file.write("{}{}{}\n\n".format(link_declaration, header, children_string))
        except:
            exclaimError("Critical error while generating the file for [{}]".format(nspace.file_name))

    def generateNamespaceChildrenString(self, nspace):
        '''
        Helper method for :func:`exhale.ExhaleRoot.generateSingleNamespace`, and
        :func:`exhale.ExhaleRoot.generateFileNodeDocuments`.  Builds the
        body text for the namespace node document that links to all of the child
        namespaces, structs, classes, functions, typedefs, unions, and variables
        associated with this namespace.

        :Parameters:
            ``nspace`` (ExhaleNode)
                The namespace node we are generating the body text for.

        :Return (str):
            The string to be written to the namespace node's reStructuredText document.
        '''
        # sort the children
        nsp_namespaces        = []
        nsp_nested_class_like = []
        nsp_enums             = []
        nsp_functions         = []
        nsp_typedefs          = []
        nsp_unions            = []
        nsp_variables         = []
        for child in nspace.children:
            if child.kind == "namespace":
                nsp_namespaces.append(child)
            elif child.kind == "struct" or child.kind == "class":
                child.findNestedClassLike(nsp_nested_class_like)
                child.findNestedEnums(nsp_enums)
                child.findNestedUnions(nsp_unions)
            elif child.kind == "enum":
                nsp_enums.append(child)
            elif child.kind == "function":
                nsp_functions.append(child)
            elif child.kind == "typedef":
                nsp_typedefs.append(child)
            elif child.kind == "union":
                nsp_unions.append(child)
            elif child.kind == "variable":
                nsp_variables.append(child)

        # generate their headings if they exist (no Defines...that's not a C++ thing...)
        children_stream = StringIO()
        self.generateSortedChildListString(children_stream, "Namespaces", nsp_namespaces)
        self.generateSortedChildListString(children_stream, "Classes", nsp_nested_class_like)
        self.generateSortedChildListString(children_stream, "Enums", nsp_enums)
        self.generateSortedChildListString(children_stream, "Functions", nsp_functions)
        self.generateSortedChildListString(children_stream, "Typedefs", nsp_typedefs)
        self.generateSortedChildListString(children_stream, "Unions", nsp_unions)
        self.generateSortedChildListString(children_stream, "Variables", nsp_variables)
        # read out the buffer contents, close it and return the desired string
        children_string = children_stream.getvalue()
        children_stream.close()
        return children_string

    def generateSortedChildListString(self, stream, sectionTitle, lst):
        '''
        Helper method for :func:`exhale.ExhaleRoot.generateNamespaceChildrenString`.
        Used to build up a continuous string with all of the children separated out into
        titled sections.

        This generates a new titled section with ``sectionTitle`` and puts a link to
        every node found in ``lst`` in this section.  The newly created section is
        appended to the existing ``stream`` buffer.

        :Parameters:
            ``stream`` (StringIO)
                The already-open StringIO to write the result to.

            ``sectionTitle`` (str)
                The title of the section for this list of children.

            ``lst`` (list)
                A list of ExhaleNode objects that are to be linked to from this section.
                This method sorts ``lst`` in place.
        '''
        if lst:
            lst.sort()
            stream.write(textwrap.dedent('''

                {heading}
                {heading_mark}

            '''.format(heading=sectionTitle, heading_mark=configs.SUB_SECTION_HEADING)))
            for l in lst:
                stream.write(textwrap.dedent('''
                    - :ref:`{link}`
                '''.format(link=l.link_name)))

    def generateFileNodeDocuments(self):
        '''
        Generates the reStructuredText documents for files as well as the file's
        program listing reStructuredText document if applicable.  Refer to
        :ref:`usage_customizing_file_pages` for changing the output of this method.
        The remainder of the file lists all nodes that have been discovered to be
        defined (e.g. classes) or referred to (e.g. included files or files that include
        this file).
        '''
        for f in self.files:
            # if the programlisting was included, length will be at least 1 line
            if len(f.program_listing) > 0:
                include_program_listing = True
                full_program_listing = '.. code-block:: cpp\n\n'

                # need to reformat each line to remove xml tags / put <>& back in
                for pgf_line in f.program_listing:
                    fixed_whitespace = re.sub(r'<sp/>', ' ', pgf_line)
                    # for our purposes, this is good enough:
                    #     http://stackoverflow.com/a/4869782/3814202
                    no_xml_tags  = re.sub(r'<[^<]+?>', '', fixed_whitespace)
                    revive_lt    = re.sub(r'&lt;', '<', no_xml_tags)
                    revive_gt    = re.sub(r'&gt;', '>', revive_lt)
                    revive_quote = re.sub(r'&quot;', '"', revive_gt)
                    revive_apos  = re.sub(r'&apos;', "'", revive_quote)
                    revive_amp   = re.sub(r'&amp;', '&', revive_apos)
                    full_program_listing = "{}   {}".format(full_program_listing, revive_amp)

                # create the programlisting file
                try:
                    with open(f.program_file, "w") as gen_file:
                        # generate a link label for every generated file
                        link_declaration = ".. _{}:".format(f.program_link_name)
                        # every generated file must have a header for sphinx to be happy
                        prog_title = "Program Listing for {} {}".format(qualifyKind(f.kind), f.name)
                        gen_file.write(textwrap.dedent('''
                            {link}

                            {heading}
                            {heading_mark}

                            - Return to documentation for :ref:`{parent}`

                        '''.format(
                            link=link_declaration, heading=prog_title,
                            heading_mark=configs.SECTION_HEADING,
                            parent=f.link_name,
                        )))
                        gen_file.write(full_program_listing)
                except:
                    exclaimError("Critical error while generating the file for [{}]".format(f.file_name))
            else:
                include_program_listing = False

        for f in self.files:
            if len(f.location) > 0:
                file_definition = textwrap.dedent('''
                    Definition (``{where}``)
                    {heading_mark}

                '''.format(where=f.location, heading_mark=configs.SUB_SECTION_HEADING))
            else:
                file_definition = ""

            if include_program_listing and file_definition != "":
                prog_file_definition = textwrap.dedent('''
                    .. toctree::
                       :maxdepth: 1

                       {prog_link}
                '''.format(prog_link=f.program_file.split("/")[-1]))
                file_definition = "{}{}".format(file_definition, prog_file_definition)

            if len(f.includes) > 0:
                file_includes_stream = StringIO()
                file_includes_stream.write(textwrap.dedent('''
                    Includes
                    {heading_mark}

                '''.format(heading_mark=configs.SUB_SECTION_HEADING)))
                for incl in sorted(f.includes):
                    local_file = None
                    for incl_file in self.files:
                        if incl in incl_file.location:
                            local_file = incl_file
                            break
                    if local_file is not None:
                        file_includes_stream.write(textwrap.dedent('''
                            - ``{include}`` (:ref:`{link}`)
                        '''.format(include=incl, link=local_file.link_name)))
                    else:
                        file_includes_stream.write(textwrap.dedent('''
                            - ``{include}``
                        '''.format(include=incl)))

                file_includes = file_includes_stream.getvalue()
                file_includes_stream.close()
            else:
                file_includes = ""

            if len(f.included_by) > 0:
                file_included_by_stream = StringIO()
                file_included_by_stream.write(textwrap.dedent('''
                    Included By
                    {heading_mark}

                '''.format(heading_mark=configs.SUB_SECTION_HEADING)))
                for incl_ref, incl_name in f.included_by:
                    for incl_file in self.files:
                        if incl_ref == incl_file.refid:
                            file_included_by_stream.write(textwrap.dedent('''
                                - :ref:`{link}`
                            '''.format(link=incl_file.link_name)))
                            break
                file_included_by = file_included_by_stream.getvalue()
                file_included_by_stream.close()
            else:
                file_included_by = ""

            # generate their headings if they exist --- DO NOT USE findNested*, these are included recursively
            file_structs    = []
            file_classes    = []
            file_enums      = []
            file_functions  = []
            file_typedefs   = []
            file_unions     = []
            file_variables  = []
            file_defines    = []
            for child in f.children:
                if child.kind == "struct":
                    file_structs.append(child)
                elif child.kind == "class":
                    file_classes.append(child)
                elif child.kind == "enum":
                    file_enums.append(child)
                elif child.kind == "function":
                    file_functions.append(child)
                elif child.kind == "typedef":
                    file_typedefs.append(child)
                elif child.kind == "union":
                    file_unions.append(child)
                elif child.kind == "variable":
                    file_variables.append(child)
                elif child.kind == "define":
                    file_defines.append(child)

            # generate the listing of children referenced to from this file
            children_stream = StringIO()
            self.generateSortedChildListString(children_stream, "Namespaces", f.namespaces_used)
            self.generateSortedChildListString(children_stream, "Classes", file_structs + file_classes)
            self.generateSortedChildListString(children_stream, "Enums", file_enums)
            self.generateSortedChildListString(children_stream, "Functions", file_functions)
            self.generateSortedChildListString(children_stream, "Defines", file_defines)
            self.generateSortedChildListString(children_stream, "Typedefs", file_typedefs)
            self.generateSortedChildListString(children_stream, "Unions", file_unions)
            self.generateSortedChildListString(children_stream, "Variables", file_variables)

            children_string = children_stream.getvalue()
            children_stream.close()

            # acquire the file level documentation if present.
            #
        #possible keys for this dictionary on files:
        # ['@id', '@kind', '@language', 'compoundname', 'includes', 'includedby',
        # 'incdepgraph', 'invincdepgraph', 'innerclass', 'innernamespace',
        # 'briefdescription', 'detaileddescription', 'programlisting', 'location']
        #believe is same for all kinds, need to verify
            # cdef_dict = f.openNodeCompoundDefDict()
            # brief = cdef_dict["briefdescription"]
            # detailed = cdef_dict["detaileddescription"]

            try:
                with open(f.file_name, "w") as gen_file:
                    # generate a link label for every generated file
                    link_declaration = ".. _{}:".format(f.link_name)
                    # every generated file must have a header for sphinx to be happy
                    f.title = "{} {}".format(qualifyKind(f.kind), f.name)
                    heading = textwrap.dedent('''
                        :tocdepth: {page_depth}

                        {link}

                        {heading}
                        {heading_mark}
                    '''.format(
                        page_depth=configs.exhaleApiPageTocDepth, link=link_declaration, heading=f.title, heading_mark=configs.SECTION_HEADING
                    ))

                    brief, detailed = parse.getFileBriefAndDetailedRST(self, f)
                    gen_file.write(textwrap.dedent('''
                        {heading}

                        {brief}

                        {definition}

                        {detailed}

                        {includes}

                        {includeby}

                        {children}
                    '''.format(
                        heading=heading, brief=brief, definition=file_definition,
                        detailed=detailed, includes=file_includes,
                        includeby=file_included_by, children=children_string
                    )).lstrip())
            except Exception as e:
                exclaimError("Critical error while generating the file for [{}]:\n{}".format(f.file_name, e))

            if configs.generateBreatheFileDirectives:
                try:
                    with open(f.file_name, "a") as gen_file:
                        # add the breathe directive ???
                        gen_file.write(
                            "\nFull File Listing\n{0}\n\n"
                            ".. {1}:: {2}\n"
                            "{3}\n\n".format(
                                configs.SUB_SECTION_HEADING, kindAsBreatheDirective(f.kind),
                                f.location, specificationsForKind(f.kind)
                            )
                        )

                except:
                    exclaimError(
                        "Critical error while generating the breathe directive for [{}]".format(f.file_name)
                    )

    def generateDirectoryNodeDocuments(self):
        '''
        Generates all of the directory reStructuredText documents.
        '''
        all_dirs = []
        for d in self.dirs:
            d.findNestedDirectories(all_dirs)

        for d in all_dirs:
            self.generateDirectoryNodeRST(d)

    def generateDirectoryNodeRST(self, node):
        '''
        Helper method for :func:`exhale.ExhaleRoot.generateDirectoryNodeDocuments`.
        Generates the reStructuredText documents for the given directory node.
        Directory nodes will only link to files and subdirectories within it.

        :Parameters:
            ``node`` (ExhaleNode)
                The directory node to generate the reStructuredText document for.
        '''
        # find the relevant children: directories and files only
        child_dirs  = []
        child_files = []
        for c in node.children:
            if c.kind == "dir":
                child_dirs.append(c)
            elif c.kind == "file":
                child_files.append(c)

        # generate the subdirectory section
        if len(child_dirs) > 0:
            child_dirs_string = "Subdirectories\n{}\n\n".format(configs.SUB_SECTION_HEADING)
            for child_dir in sorted(child_dirs):
                child_dirs_string = "{}- :ref:`{}`\n".format(child_dirs_string, child_dir.link_name)
        else:
            child_dirs_string = ""

        # generate the files section
        if len(child_files) > 0:
            child_files_string = "Files\n{}\n\n".format(configs.SUB_SECTION_HEADING)
            for child_file in sorted(child_files):
                child_files_string = "{}- :ref:`{}`\n".format(child_files_string, child_file.link_name)
        else:
            child_files_string = ""

        # generate the file for this directory
        try:
            with open(node.file_name, "w") as gen_file:
                # generate a link label for every generated file
                link_declaration = ".. _{}:\n\n".format(node.link_name)
                header = "{}\n{}\n\n".format(node.title, configs.SECTION_HEADING)
                # generate the headings and links for the children
                # write it all out
                ###################page_toc
                gen_file.write("{}{}{}\n{}\n\n".format(
                    link_declaration, header, child_dirs_string, child_files_string)
                )
        except:
            exclaimError("Critical error while generating the file for [{}]".format(node.file_name))

    def generateAPIRootBody(self):
        '''
        Generates the root library api file's body text.  The method calls
        :func:`exhale.ExhaleRoot.gerrymanderNodeFilenames` first to enable proper
        internal linkage between reStructuredText documents.  Afterward, it calls
        :func:`exhale.ExhaleRoot.generateViewHierarchies` followed by
        :func:`exhale.ExhaleRoot.generateUnabridgedAPI` to generate both hierarchies as
        well as the full API listing.  As a result, three files will now be ready:

        1. ``self.class_view_file``
        2. ``self.directory_view_file``
        3. ``self.unabridged_api_file``

        These three files are then *included* into the root library file.  The
        consequence of using an ``include`` directive is that Sphinx will complain about
        these three files never being included in any ``toctree`` directive.  These
        warnings are expected, and preferred to using a ``toctree`` because otherwise
        the user would have to click on the class view link from the ``toctree`` in
        order to see it.  This behavior has been acceptable for me so far, but if it
        is causing you problems please raise an issue on GitHub and I may be able to
        conditionally use a ``toctree`` if you really need it.
        '''
        try:
            self.gerrymanderNodeFilenames()
            self.generateViewHierarchies()
            self.generateUnabridgedAPI()
            with open(self.full_root_file_path, "a") as generated_index:
                generated_index.write(
                    ".. include:: {}\n\n".format(self.class_view_file.split("/")[-1])
                )
                generated_index.write(
                    ".. include:: {}\n\n".format(self.directory_view_file.split("/")[-1])
                )
                generated_index.write(
                    ".. include:: {}\n\n".format(self.unabridged_api_file.split("/")[-1])
                )
        except Exception as e:
            exclaimError("Unable to create the root api body: {}".format(e))

    def gerrymanderNodeFilenames(self):
        '''
        When creating nodes, the filename needs to be relative to ``conf.py``, so it
        will include ``self.root_directory``.  However, when generating the API, the
        file we are writing to is in the same directory as the generated node files so
        we need to remove the directory path from a given ExhaleNode's ``file_name``
        before we can ``include`` it or use it in a ``toctree``.
        '''
        for node in self.all_nodes:
            node.file_name = node.file_name.split("/")[-1]
            if node.kind == "file":
                node.program_file = node.program_file.split("/")[-1]

    def generateViewHierarchies(self):
        '''
        Wrapper method to create the view hierarchies.  Currently it just calls
        :func:`exhale.ExhaleRoot.generateClassView` and
        :func:`exhale.ExhaleRoot.generateDirectoryView` --- if you want to implement
        additional hierarchies, implement the additionaly hierarchy method and call it
        from here.  Then make sure to ``include`` it in
        :func:`exhale.ExhaleRoot.generateAPIRootBody`.
        '''
        self.generateClassView(self.use_tree_view)
        self.generateDirectoryView(self.use_tree_view)

    def generateClassView(self, treeView):
        '''
        Generates the class view hierarchy, writing it to ``self.class_view_file``.

        :Parameters:
            ``treeView`` (bool)
                Whether or not to use the collapsibleList version.  See the
                ``createTreeView`` description in :func:`exhale.generate`.
        '''
        class_view_stream = StringIO()

        for n in self.namespaces:
            n.toClassView(0, class_view_stream, treeView)

        # Add everything that was not nested in a namespace.
        missing = []
        # class-like objects (structs and classes)
        for cl in sorted(self.class_like):
            if not cl.in_class_view:
                missing.append(cl)
        # enums
        for e in sorted(self.enums):
            if not e.in_class_view:
                missing.append(e)
        # unions
        for u in sorted(self.unions):
            if not u.in_class_view:
                missing.append(u)

        if len(missing) > 0:
            idx = 0
            last_missing_child = len(missing) - 1
            for m in missing:
                m.toClassView(0, class_view_stream, treeView, idx == last_missing_child)
                idx += 1
        elif treeView:
            # need to restart since there were no missing children found, otherwise the
            # last namespace will not correctly have a lastChild
            class_view_stream.close()
            class_view_stream = StringIO()

            last_nspace_index = len(self.namespaces) - 1
            for idx in range(last_nspace_index + 1):
                nspace = self.namespaces[idx]
                nspace.toClassView(0, class_view_stream, treeView, idx == last_nspace_index)

        # extract the value from the stream and close it down
        class_view_string = class_view_stream.getvalue()
        class_view_stream.close()

        # inject the raw html for the treeView unordered lists
        if treeView:
            # we need to indent everything to be under the .. raw:: html directive, add
            # indentation so the html is readable while we are at it
            indented = re.sub(r'(.+)', r'        \1', class_view_string)
            class_view_string =                               \
                '.. raw:: html\n\n'                           \
                '   <ul class="treeView">\n'                  \
                '     <li>\n'                                 \
                '       <ul class="collapsibleList">\n'       \
                '{}'                                          \
                '       </ul><!-- collapsibleList -->\n'      \
                '     </li><!-- only tree view element -->\n' \
                '   </ul><!-- treeView -->\n'.format(indented)

        # write everything to file to be included in the root api later
        try:
            with open(self.class_view_file, "w") as cvf:
                cvf.write("Class Hierarchy\n{}\n\n{}\n\n".format(configs.SUB_SECTION_HEADING,
                                                                 class_view_string))
        except Exception as e:
            exclaimError("Error writing the class hierarchy: {}".format(e))

    def generateDirectoryView(self, treeView):
        '''
        Generates the file view hierarchy, writing it to ``self.directory_view_file``.

        :Parameters:
            ``treeView`` (bool)
                Whether or not to use the collapsibleList version.  See the
                ``createTreeView`` description in :func:`exhale.generate`.
        '''
        directory_view_stream = StringIO()

        for d in self.dirs:
            d.toDirectoryView(0, directory_view_stream, treeView)

        # add potential missing files (not sure if this is possible though)
        missing = []
        for f in sorted(self.files):
            if not f.in_directory_view:
                missing.append(f)

        found_missing = len(missing) > 0
        if found_missing:
            idx = 0
            last_missing_child = len(missing) - 1
            for m in missing:
                m.toDirectoryView(0, directory_view_stream, treeView, idx == last_missing_child)
                idx += 1
        elif treeView:
            # need to restart since there were no missing children found, otherwise the
            # last directory will not correctly have a lastChild
            directory_view_stream.close()
            directory_view_stream = StringIO()

            last_dir_index = len(self.dirs) - 1
            for idx in range(last_dir_index + 1):
                curr_d = self.dirs[idx]
                curr_d.toDirectoryView(0, directory_view_stream, treeView, idx == last_dir_index)

        # extract the value from the stream and close it down
        directory_view_string = directory_view_stream.getvalue()
        directory_view_stream.close()

        # inject the raw html for the treeView unordered lists
        if treeView:
            indented = re.sub(r'(.+)', r'        \1', directory_view_string)
            if configs.treeViewIsBootstrap:
                directory_view_string =                           \
                    '.. raw:: html\n\n'                           \
                    '   <div id="directory-treeView"></div>\n\n'  \
                    '   <script type="text/javascript">\n'        \
                    '     function getDirectoryViewTree() {{\n'   \
                    '       return [\n'                           \
                    '{}'                                          \
                    '       ];\n'                                 \
                    '     }}\n'                                   \
                    '   </script>\n'.format(indented)
            else:
                # we need to indent everything to be under the .. raw:: html directive, add
                # indentation so the html is readable while we are at it
                directory_view_string =                           \
                    '.. raw:: html\n\n'                           \
                    '   <ul class="treeView">\n'                  \
                    '     <li>\n'                                 \
                    '       <ul class="collapsibleList">\n'       \
                    '{}'                                          \
                    '       </ul><!-- collapsibleList -->\n'      \
                    '     </li><!-- only tree view element -->\n' \
                    '   </ul><!-- treeView -->\n'.format(indented)

        # write everything to file to be included in the root api later
        try:
            with open(self.directory_view_file, "w") as dvf:
                dvf.write("File Hierarchy\n{}\n\n{}\n\n".format(configs.SUB_SECTION_HEADING,
                                                                directory_view_string))
        except Exception as e:
            exclaimError("Error writing the directory hierarchy: {}".format(e))

    def generateUnabridgedAPI(self):
        '''
        Generates the unabridged (full) API listing into ``self.unabridged_api_file``.
        This is necessary as some items may not show up in either hierarchy view,
        depending on:

        1. The item.  For example, if a namespace has only one member which is a
           variable, then neither the namespace nor the variable will be declared in the
           class view hierarchy.  It will be present in the file page it was declared in
           but not on the main library page.

        2. The configurations of Doxygen.  For example, see the warning in
           :func:`exhale.ExhaleRoot.fileRefDiscovery`.  Items whose parents cannot be
           rediscovered withouth the programlisting will still be documented, their link
           appearing in the unabridged API listing.

        Currently, the API is generated in the following (somewhat arbitrary) order:

        - Namespaces
        - Classes and Structs
        - Enums
        - Unions
        - Functions
        - Variables
        - Defines
        - Typedefs
        - Directories
        - Files

        If you want to change the ordering, just change the order of the calls to
        :func:`exhale.ExhaleRoot.enumerateAll` in this method.
        '''
        try:
            with open(self.unabridged_api_file, "w") as full_api_file:
                # write the header
                full_api_file.write("Full API\n{}\n\n".format(configs.SUB_SECTION_HEADING))

                # recover all namespaces that were reparented
                all_namespaces = []
                for n in self.namespaces:
                    n.findNestedNamespaces(all_namespaces)

                # recover all directories that were reparented
                all_directories = []
                for d in self.dirs:
                    d.findNestedDirectories(all_directories)

                # recover classes and structs that were reparented
                all_class_like = []
                for cl in self.class_like:
                    cl.findNestedClassLike(all_class_like)

                # write everything to file: reorder these lines for different outcomes
                self.enumerateAll("Namespaces", all_namespaces, full_api_file)
                self.enumerateAll("Classes and Structs", all_class_like, full_api_file)
                self.enumerateAll("Enums", self.enums, full_api_file)
                self.enumerateAll("Unions", self.unions, full_api_file)
                self.enumerateAll("Functions", self.functions, full_api_file)
                self.enumerateAll("Variables", self.variables, full_api_file)
                self.enumerateAll("Defines", self.defines, full_api_file)
                self.enumerateAll("Typedefs", self.typedefs, full_api_file)
                self.enumerateAll("Directories", all_directories, full_api_file)
                self.enumerateAll("Files", self.files, full_api_file)
        except Exception as e:
            exclaimError("Error writing the unabridged API: {}".format(e))

    def enumerateAll(self, subsectionTitle, lst, openFile):
        '''
        Helper function for :func:`exhale.ExhaleRoot.generateUnabridgedAPI`.  Simply
        writes a subsection to ``openFile`` (a ``toctree`` to the ``file_name``) of each
        ExhaleNode in ``sorted(lst)`` if ``len(lst) > 0``.  Otherwise, nothing is
        written to the file.

        :Parameters:
            ``subsectionTitle`` (str)
                The title of this subsection, e.g. ``"Namespaces"`` or ``"Files"``.

            ``lst`` (list)
                The list of ExhaleNodes to be enumerated in this subsection.

            ``openFile`` (File)
                The **already open** file object to write to directly.  No safety checks
                are performed, make sure this is a real file object that has not been
                closed already.
        '''
        if len(lst) > 0:
            openFile.write("{}\n{}\n\n".format(subsectionTitle, configs.SUB_SUB_SECTION_HEADING))
            for l in sorted(lst):
                openFile.write(
                    ".. toctree::\n"
                    "   :maxdepth: {}\n\n"
                    "   {}\n\n".format(configs.exhaleApiTocTreeMaxDepth, l.file_name)
                )

    def generateAPIRootSummary(self):
        '''
        Writes the library API root summary to the main library file.  See the
        documentation for the key ``afterBodySummary`` in :func:`exhale.generate`.
        '''
        try:
            with open(self.full_root_file_path, "a") as generated_index:
                generated_index.write("{}\n\n".format(self.root_file_summary))
        except Exception as e:
            exclaimError("Unable to create the root api summary: {}".format(e))

    ####################################################################################
    #
    ##
    ### Miscellaneous utility functions.
    ##
    #
    ####################################################################################
    def toConsole(self):
        '''
        Convenience function for printing out the entire API being generated to the
        console.  Unused in the release, but is helpful for debugging ;)
        '''
        self.consoleFormat("Classes and Structs", self.class_like)
        self.consoleFormat("Defines", self.defines)
        self.consoleFormat("Enums", self.enums)
        self.consoleFormat("Enum Values", self.enum_values)
        self.consoleFormat("Functions", self.functions)
        self.consoleFormat("Files", self.files)
        self.consoleFormat("Directories", self.dirs)
        self.consoleFormat("Groups", self.groups)
        self.consoleFormat("Namespaces", self.namespaces)
        self.consoleFormat("Typedefs", self.typedefs)
        self.consoleFormat("Unions", self.unions)
        self.consoleFormat("Variables", self.variables)

    def consoleFormat(self, sectionTitle, lst):
        '''
        Helper method for :func:`exhale.ExhaleRoot.toConsole`.  Prints the given
        ``sectionTitle`` and calls :func:`exhale.ExhaleNode.toConsole` with ``0`` as the
        level for every ExhaleNode in ``lst``.

        :Parameters:
            ``sectionTitle`` (str)
                The title that will be printed with some visual separators around it.

            ``lst`` (list)
                The list of ExhaleNodes to print to the console.
        '''
        print("###########################################################")
        print("## {}".format(sectionTitle))
        print("###########################################################")
        for l in lst:
            l.toConsole(0)
