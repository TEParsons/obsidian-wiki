from .utils import Path, pathlike, logging
import markdown as md
from copy import deepcopy
import shutil
import os
import re
import argparse


encoding = 'utf-8'
logging.getLogger().setLevel(logging.INFO)
__folder__ = Path(__file__).parent


class Wiki:
    """
    Object representing a full wiki.
    
    #### Parameters
    name (str)
    :    Name of the wiki.
    source (pathlike)
    :    Folder with all of the markdown files in.
    dest (pathlike)
    :    Folder you want all the html files to go in.
    templates (pathlike, None)
    :    Folder containing html templates to use, named according to possible "tag" values in md YAML defs. If "tag" isn't present, will use "default". Defaults to None.
    interpreter (markdown.Markdown, None)
    :    Markdown interpreter to use. Defaults to None.
    """
    def __init__(
            self,
            name: str,
            source: pathlike,
            dest: pathlike,
            templates=None,
            interpreter=None
    ):        
        self.name = name
        # Store source and destination folders
        self.source = Path(source)
        self.dest = Path(dest)
        # Array to store page objects in
        self.pages = []
        # If templates is None, use default templates folder
        if templates is None:
            templates = __folder__ / "templates"
        self.templates_folder = templates
        # Store/create interpreter
        self.md = interpreter
        if self.md is None:
            self.md = md.Markdown(extensions=["extra", "admonition", "nl2br"])
        # Get wiki-level metadata
        self.meta = self.get_meta()
        print(self.meta)
    
    def get_meta(self):
        # Setup parser to read metadata
        parser = md.Markdown(extensions=["meta"])
        # Find index file of this wiki (if any)
        index_file = None
        for name in (
            "index.md",
            "home.md",
            f"{self.name}.md",
            f"{self.name.lower()}.md",
            f"{self.name.upper()}.md",
            f"{self.name.title()}.md",
        ):
            if (self.source / name).is_file():
                index_file = self.source / name
        # If no index file, return blank
        if index_file is None:
            return {}
        # Read index file
        content = index_file.read_text(encoding=encoding)
        # Get metadata
        parser.convert(content)
        return parser.Meta
    
    @property
    def templates_folder(self):
        return self._templates_folder
    
    @templates_folder.setter
    def templates_folder(self, value):
        # Clear templates dict
        self.templates = {}
        # Read in templates from folder
        logging.start_delim("Reading templates...")
        for template_file in Path(value).glob("*.html"):
            self.templates[template_file.stem] = template_file.read_text(encoding=encoding)
            logging.info(f"{template_file.stem}: {template_file}")
        # Make sure we have a default template
        if "default" not in self.templates:
            self.templates['default'] = (__folder__ / "templates" / "default.html").read_text(encoding=encoding)
            logging.info("No default template found. Using module default instead.")
        # Make sure we have a home template
        if "default" not in self.templates:
            self.templates['home'] = (__folder__ / "templates" / "home.html").read_text(encoding=encoding)
            logging.info("No default template found. Using module default instead.")
        # Log success
        logging.end_delim("Finished reading templates.")
    
    def get_page_from_path(self, page):
        """
        Get the WikiPage object for a page from the path of its markdown file.
        
        #### Parameters
        page (pathlike)
        :    Path to the desired page's markdown file, can be absolute or relative to wiki root.
        """
        # Convert to Path object
        path = Path(path)
        # Make absolute
        if not path.is_absolute():
            path = self.source / path
        # Check source path of each page
        for obj in self.pages:
            if obj.source == Path(page):
                return obj
        
    def compile(self):
        logging.start_delim("Configuring output folder...")
        # Clear build folder
        if self.dest.is_dir():
            shutil.rmtree(self.dest)
            logging.info(f"Deleted folder {self.dest}")
        os.mkdir(str(self.dest))
        logging.info(f"Created folder {self.dest}")
        # Copy style, assets and scripts over
        for key in ("assets", "style", "utils"):
            # Copy source folder if there is one
            if (self.source / ("_" + key)).is_dir():
                shutil.copytree(
                    self.source / ("_" + key),
                    self.dest / key
                )
                logging.info(f"Copied {self.source / key} to {self.dest / key}.")
        logging.end_delim("Finished configuring output folder.")
        # Build every md file in source tree
        logging.start_delim("Building pages...")
        self.pages = []
        for file in self.source.glob("**/*.md"):
            if file.parent == self.source and file.stem.lower() in ("index", self.name.lower()):
                # For homepage, make special homepage object
                page = WikiHomepage(
                    wiki=self,
                    source=file,
                    dest=self.dest / file.relative_to(self.source).parent,
                    template="home"
                )
            else:
                # For the rest, make a general page object
                page = WikiPage(
                    wiki=self,
                    source=file,
                    dest=self.dest / file.relative_to(self.source).parent
                )
            self.pages.append(page)
        for page in self.pages:
            page.compile(save=True)
        logging.end_delim("Finished building.")


class WikiPage:
    def __init__(
            self,
            wiki: Wiki,
            source: pathlike,
            dest: pathlike,
            template="default",
    ):
        """
        An indiviual page of a wiki.

        #### Parameters
        wiki : Wiki
            Wiki which this page sits within
        source : Path, str
            Markdown file to read in
        dest : Path, str
            Folder to write HTML file to
        template : str
            Which of the Wiki's template HTML files to use
        """
        self.wiki = wiki
        self.source = source
        self.dest = dest
        self.template = template
        self.breadcrumbs = Breadcrumbs(page=self)
        self.navbar = NavBar(page=self)
    
    @property
    def source(self):
        return self._source
    
    @source.setter
    def source(self, value):
        # Store source ref
        self._source = Path(value)
        # Read source file
        logging.info(f"Read '{self.source.relative_to(self.wiki.source)}'")
        self.content_md = self.source.read_text(encoding=encoding)
        # Set title
        if self.is_home:
            self.title = self.wiki.name
        elif self.is_index:
            self.title = self._source.parent.stem
        else:
            self.title = self._source.stem

    @property
    def dest(self):
        return self._dest
    
    @dest.setter
    def dest(self, value):
        self._dest = Path(value)

    @property
    def template(self):
        return self._template
    
    @template.setter
    def template(self, value):
        """
        Set this page's template from the dict of templates in its wiki object.
        """
        if value in self.wiki.templates:
            # Get template from wiki
            self._template = self.wiki.templates[value]
        else:
            # Use default if template not found, but warn
            self._template = self.wiki.templates['default']
            logging.warn(f"No template '{value}' for Wiki '{self.wiki.name}'. Using default.\n")
    
    @property
    def is_index(self):
        """
        Is this the index page of a folder?
        """
        return self.source.stem.lower() in ("index", self.source.parent.stem.lower())

    @property
    def is_home(self):
        """
        Is this the homepage of the whole wiki?
        """
        return self._source.parent == self.wiki.source and self._source.stem.lower() in ("index", "home", self.wiki.name.lower())
    
    def compile(self, save=False):
        def preprocess(content):
            """
            Transformations to apply to markdown content before compiling to HTML
            """
            # Style IPA strings
            def _ipa(match):
                ipa = match.group(1)
                return f"<a class=ipa href=http://ipa-reader.xyz/?text={ipa}&voice=Brian>{ipa}</a>"
            content = re.sub(r"^\/(.{1,})\/$", _ipa, content, flags=re.MULTILINE)

            # Insert contents from markmoji-style syntax
            def _contents(match):
                title = match.group(1)
                path = Path(match.group(2))
                # Resolve relative paths
                if not path.is_absolute():
                    path = (self.source.parent / path).resolve()
                # Construct Contents object
                obj = Contents(
                    page=self,
                    path=path,
                    title=title
                )

                return str(obj)
            content = re.sub(r"📑\[(.*)\]\((.*)\)", _contents, content, flags=re.MULTILINE)

            # Replace refs to markdown files with refs to equivalent html files
            def _links(match):
                label = match.group(1)
                path = match.group(2)
                # Remove spaces from link stem
                path = path.replace(" ", "").replace("%20", "")
                # Replace .md with .html
                return f"[{label}]({path}.html)"
            content = re.sub(r"\[(.*)\]\((.*)\.md\)", _links, content, flags=re.MULTILINE)
            
            return content

        def postprocess(content):
            """
            Transformations to apply to HTML content after compiling from markdown
            """

            return content
        
        # Copy template and content
        page = deepcopy(self.template)
        content_md = deepcopy(self.content_md)

        # Add breadcrumbs
        page = page.replace("{{breadcrumbs}}", str(self.breadcrumbs))

        # Update tab title
        if self.is_home:
            page = page.replace("{{stem}}", f"{self.wiki.name}")
        else:
            page = page.replace("{{stem}}", f"{self.wiki.name}: {self.title}")
        
        # Update header
        page = page.replace("{{title}}", self.wiki.name)
        page = page.replace("{{nav}}", str(self.navbar))

        # Update page title (if there isn't one)
        if not content_md.startswith("# ") and not isinstance(self, WikiHomepage):
            content_md = (
                f"# {self.title}\n"
                f"{content_md}"
                )

        # Transpile html content
        content_md = preprocess(content_md)
        content_html = self.wiki.md.convert(content_md)
        content_html = postprocess(content_html)

        # Store html content
        self.content_html = content_html
        logging.info(f"Transpiled '{self.source.relative_to(self.wiki.source)}' to HTML.")

        # Insert content into page
        page = page.replace("{{content}}", content_html)

        # Normalize paths
        for key in ("root", "style", "utils"):
            norm = self.wiki.source.normalize(self.source)
            if key != "root":
                norm /= key
            page = page.replace("{{%s}}" % key, str(norm).replace("\\", "/"))
        # Remove underscore from assets links
        page = page.replace("_assets/", "assets/")

        # Store full page content
        self.page = page

        if save:
            self.save()
    
    def save(self):
        # Get file name - use index for index pages
        if self.is_index:
            stem = "index"
        else:
            stem = self.source.stem
        # Construct destination file
        stem = stem.replace(" ", "").replace("%20", "")
        dest = self.dest / (stem + ".html")
        # Make sure directory exists
        if not dest.parent.is_dir():
            os.makedirs(str(dest.parent))
            logging.info(f"Created directory {dest.parent}.")
        # Save file
        dest.write_text(self.page, encoding=encoding)
        logging.info(f"Written {dest.relative_to(self.wiki.dest)}.")


class WikiHomepage(WikiPage):
    """
    The main page of a wiki - like a WikiPage in most respects, but with 
    different contents and no breadcrumbs.

    wiki (Wiki)
    :    Wiki which this page sits within
    source (Path, str)
    :    Markdown file to read in
    dest (Path, str)
    :    Folder to write HTML file to
    template (str)
    :    Which of the Wiki's template HTML files to use
    """
    def __init__(
            self,
            wiki: Wiki,
            source: pathlike,
            dest: pathlike,
            template="home",
    ):
        # Initialise as normal
        WikiPage.__init__(
            self, 
            wiki=wiki, 
            source=source, 
            dest=dest, 
            template=template
        )
        # Create a contents object for each folder instead of one big one
        self.contents = ContentsArray()
        for folder in sorted(self.source.parent.glob("*/"), key=lambda m: m.stem):
            indexed = (folder / "index.md").is_file() or (folder / f"{folder.stem}.md").is_file()
            if folder.is_dir() and indexed and not folder.stem.startswith("_") and not folder.stem.startswith("."):
                self.contents[folder.stem] = Contents(page=self, path=folder)


class Breadcrumbs:
    """
    Array of links pointing back to the Wiki source.
    
    #### Parameters
    page (WikiPage)
    :    Page which these breadcrumbs belong to.
    """

    class Crumb:
        def __init__(
                self,
                page:WikiPage,
                file:Path
            ):
            # Get link
            root = Path()
            parents = list(page.source.relative_to(file).parents)
            for n in parents[:-1]:
                root /= ".."
            self.href = root
            # Get name
            stem = file.stem
            if stem in ("", page.wiki.source.stem):
                stem = "Home"
            self.label = stem
        
        def __str__(self):
            return f"<li><a href={self.href}>{self.label}</a></li>\n"

    def __init__(
            self,
            page:WikiPage
        ):
        self.page = page
        self.wiki = self.page.wiki

        # Get list of parents
        self.parents = list(self.page.source.relative_to(self.wiki.source).parents)
        self.parents.reverse()
        # Turn them into crumbs
        self.crumbs = []
        for file in self.parents:
            # Don't make crumb for folder if this is its index file
            if file.stem == self.page.source.parent.stem:
                continue
            # Make a crumb for this level
            crumb = self.Crumb(
                page=self.page,
                file=(self.wiki.source / file).resolve()
            )
            self.crumbs.append(crumb)
    
    def __str__(self):
        # If we're at the absolute root, breadcrumbs are blank
        if self.page.source.parent == self.wiki.source:
            return ""
        
        # Start breadcrumbs
        breadcrumbs = "<ul class=wiki-breadcrumbs>\n"
        # Stringify crumbs
        for crumb in self.crumbs:
            breadcrumbs += str(crumb)
        # End breadcrumbs
        breadcrumbs += "</ul>"
        
        return breadcrumbs


class Contents:
    """
    Contents list for a folder within this Wiki.
    
    #### Parameters
    page (WikiPage)
    :    Page to create links relative to.
    path (pathlike, None)
    :    Path of the folder to create contents for, leave as None to point to page parent.
    """
        
    class PageLink:
        def __init__(
                self,
                page:WikiPage,
                file:Path,
        ):
            self.href = file.relative_to(page.source.parent).parent / file.stem.replace(" ", "").replace("%20", "")
            self.label = file.stem
        
        def __str__(self):
            return f"<a href={self.href}><li class=wiki-contents-page>{self.label}</li></a>"

    class FolderLink:
        def __init__(
                self,
                page:WikiPage,
                folder:Path
        ):
            # Get own params
            self.href = folder.relative_to(page.source.parent).parent / folder.stem
            self.label = folder.stem
            # First do folders
            self.items = []
            for file in sorted(folder.glob("*/"), key=lambda m: m.stem):
                indexed = (file / "index.md").is_file() or (file / f"{file.stem}.md").is_file()
                if file.is_dir() and indexed and not file.stem.startswith("_") and not folder.stem.startswith("."):
                    item = Contents.FolderLink(
                        page=page,
                        folder=file
                    )
                    self.items.append(item)
            # Then do files
            for file in sorted(folder.glob("*.md"), key=lambda m: m.stem):
                if file.suffix == ".md" and file.stem not in ("index", folder.stem):
                    item = Contents.PageLink(
                        page=page,
                        file=file
                    )
                    self.items.append(item)
        
        def __str__(self):
            # Open element
            content = (
                f"<a href={self.href}><li class=wiki-contents-folder>{self.label}<ul>"
            )
            # Add each item
            for item in self.items:
                content += f"{item}\n"
            # Close element
            content += f"</ul></li></a>"

            return content 

    def __init__(
            self,
            page:WikiPage,
            path:pathlike=None,
            title:str="Contents"
    ):
        self.page = page
        self.title = title
        # Use page parent if no path given
        if path is None:
            path = page.source.parent

        # Make base-level folder
        folder = Contents.FolderLink(
            page=page,
            folder=path
        )

        self.items = folder.items
        self.href = folder.href
    
    def __str__(self):
        # Open element
        content = (
            "<ul class=wiki-contents>\n"
        )
        # Write title (if any)
        if self.title:
            content += (
                f"<h3><a href={self.href}>{self.title}</a></h3>\n"
            )
        # Add each item
        for item in self.items:
            content += f"{item}\n"
        # Close element
        content += "</ul>"

        return content


class ContentsArray(dict):
    """
    An array of names Contents objects, who stringify themselves with titles 
    and without the associated gubbins of a dict.
        
    #### Parameters
    page (WikiPage)
    :    Page to create links relative to.
    path (pathlike, None)
    :    Path of the folder to create contents for, leave as None to point to page parent.
    """
    def __str__(self):
        """
        Convert each contained Contents object to a string and concatenate.
        """
        content = ""
        for title, obj in sorted(self.items(), key=lambda m: m[0]):
            # Open element
            content += (
                f"<ul class=wiki-contents>\n"
                f"<h3>{title}</h3>\n"
            )
            # Add each item
            for item in obj.items:
                content += f"{item}\n"
            # Close element
            content += "</ul>"

        return content


class NavBar:
    def __init__(
            self,
            page:WikiPage
        ):
        """
        Navigation links for the whole wiki.
        
        #### Parameters
        page (WikiPage)
        :    Page to normalize links against
        """
        self.page = page
        self.wiki = self.page.wiki
        # Create links to each folder in wiki
        self.links = []
        for link in self.wiki.meta.get('nav-links', []):
            # Skip blank (probably a newline)
            if not link:
                continue
            # Path-ise
            link = Path(link)
            # Normalise to current page
            self.links.append(
                self.wiki.source.normalize(self.page.source) / link
            )
    
    def __str__(self):
        content = "<nav class=wiki-nav>\n"
        for link in self.links:
            content += f"\t<a href={link}>{link.stem}</a>\n"
        content += "</nav>\n"
        return content


# If running from command line...
if __name__ == "__main__":
    # Create argument parser
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("source")
    parser.add_argument("dest")
    parser.add_argument("templates")
    # Get arguments
    args = parser.parse_args()
    # Validate arguments
    assert args.name, "Wiki needs a name! Supply one with --name"
    assert args.source, "Can't compile without a source folder. Supply one with --source"
    assert args.source, "Can't compile without a destination folder. Supply one with --dest"
    # Create Wiki object
    wiki = Wiki(
        name="Iuncterra",
        source=__folder__ / "source",
        dest=__folder__ / "docs",
        templates=__folder__ / "source" / "_templates" / "html"
    )
    # Compile it
    wiki.compile()