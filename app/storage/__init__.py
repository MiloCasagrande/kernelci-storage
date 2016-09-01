# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from flask import (
    Flask,
    abort,
    after_this_request,
    render_template,
    send_from_directory
)

import datetime
import math
import os

try:
    from os import scandir
except ImportError:
    from scandir import scandir

__version__ = "2016.9"
__versionfull__ = __version__

# pylint: disable=invalid-name
app = Flask("simple-storage")
app.root_path = os.path.abspath(os.path.dirname(__file__))
app.config.from_object("storage.settings")

settings_var = os.environ.get("STORAGE_SETTINGS")
if settings_var:
    app.config.from_pyfile(settings_var, silent=True)

config_get = app.config.get

# List of available size for bytes formatting.
SIZES = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']
WEBSITE_NAME = config_get("WEBSITE_NAME")
SERVER_HEADER = "{:s}/{:s}".format(
    config_get("SERVER_HEADER"), __versionfull__)
ROOT = config_get("ROOT_DIR")


def size_format(size):
    """Format a bytes size in a human readable way.

    :param size: The number of bytes to format.
    :type size: str
    :return A formatted size string.
    :rtype str
    """
    base = 1024.0
    size_fmt = ""

    size = abs(float(size))
    if size < base:
        size_fmt = "{:.1f} {:s}".format(size, SIZES[0])
    else:
        idx = math.floor(math.log(size) / math.log(base))
        size_fmt = "{:.1f} {:s}".format(
            size / math.pow(base, idx), SIZES[idx])

    return size_fmt


def scan_dir(directory, root):
    """Parse the directory.

    :param directory: The path to scan.
    :type directory: str
    :return Yield the found values.
    """
    for entry in scandir(directory):
        values = {}
        name = entry.name
        path = os.path.join(root, entry.name)

        if entry.is_dir():
            values["path"] = path
            values["size"] = None
            values["bytes"] = None
            values["time"] = None
            values["time_iso"] = None
            values["time_sort"] = -1
            values["sort"] = "d{}".format(name.lower())
            values["type"] = "dir"
        else:
            e_stat = entry.stat()
            time = datetime.datetime.fromtimestamp(e_stat.st_mtime)

            values["path"] = path
            values["size"] = size_format(e_stat.st_size)
            values["bytes"] = e_stat.st_size
            values["time"] = "{} {}".format(time.date(), time.time())
            values["time_iso"] = time.isoformat()
            values["time_sort"] = time.timestamp()
            values["sort"] = "f{}".format(name.lower())
            values["type"] = "file"

        yield name, values


@app.context_processor
def inject_variables():
    """Inject often-used variables."""
    return dict(
        description=config_get("DESCRIPTION"),
        version=__versionfull__
    )


@app.errorhandler(404)
def page_not_found(error):
    """Render 404 errors."""
    return render_template(
        "404.html",
        page_title="{:s} - {:s}".format(WEBSITE_NAME, "Resource Not Found"),
        body_title="Resource not found"
    ), 404


@app.errorhandler(500)
def internal_server_error(error):
    """Render 500 errors."""
    return render_template(
        "500.html",
        page_title="{:s} - {:s}".format(WEBSITE_NAME, "Internal Error"),
        body_title="Internal error"
    ), 500


@app.route("/favicon.ico", methods=["GET"])
def favicon():
    """Just a placeholder to catch the favicon.ico requests."""
    abort(404)


@app.route("/", methods=["GET"])
def index():
    """The empty index page."""

    @after_this_request
    def add_header(response):
        """Inject and/or change response headers."""
        response.headers["X-Robots-Tag"] = \
            "noindex,nofollow,nosnippet,noarchive"
        response.headers["Server"] = SERVER_HEADER
        return response

    page_title = "{:s} - {:s}".format(WEBSITE_NAME, "Home Page")

    return render_template(
        "index.html",
        page_title=page_title, body_title=WEBSITE_NAME, website=WEBSITE_NAME)


@app.route("/<path:path>/", methods=["GET"])
def fs_path(path):
    """The only needed route/view."""

    @after_this_request
    def add_header(response):
        """Inject and/or change response headers."""
        response.headers["X-Robots-Tag"] = \
            "noindex,nofollow,nosnippet,noarchive"
        response.headers["Server"] = SERVER_HEADER
        return response

    t_path = os.path.join(ROOT, path)

    if path[0] != "/":
        path = "/{}".format(path)
    if path[-1] == "/":
        path = "{}/".format(path)

    if os.path.isdir(t_path):
        parent = os.path.dirname(path)
        if parent == "/":
            parent = None

        page_title = "{} - {}".format(WEBSITE_NAME, path)
        body_title = WEBSITE_NAME

        return render_template(
            "listing.html",
            entries=scan_dir(t_path, path),
            parent=parent,
            page_title=page_title,
            body_title=body_title)

    elif os.path.isfile(t_path):
        return send_from_directory(
            os.path.dirname(t_path), os.path.basename(t_path))
    else:
        abort(404)
