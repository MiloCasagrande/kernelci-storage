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

from flask_wtf import Form
from wtforms.fields import (
    StringField,
    TextAreaField
)
from wtforms.validators import (
    InputRequired,
    Length,
    NoneOf,
    ValidationError
)

import datetime
import math
import os
import re
import redis
import subprocess
import tempfile

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

app.config["SECRET_KEY"] = os.urandom(24)

config_get = app.config.get

# List of available size for bytes formatting.
SIZES = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']
PAGE_TITLE = "{}&nbsp;&#946;".format(config_get("WEBSITE_NAME"))
WEBSITE_NAME = "{}&nbsp;<sup><small>&#946;eta</small></sup>".format(
    config_get("WEBSITE_NAME"))
SERVER_HEADER = "{:s}/{:s}".format(
    config_get("SERVER_HEADER"), __versionfull__)
ROOT = config_get("ROOT_DIR")

VALID_USERNAME = re.compile(r"(^[A-Za-z0-9]{1})([A-Za-z0-9-_.]{2,31})")
DB_KEY_FORMAT = "gitci|{:s}"
REDIS_PUB_CH = "gitciuser"


class StorageException(Exception):
    """A basic error class."""
    pass


def get_db_connection():
    """Get the redis connection."""
    try:
        r = redis.StrictRedis(
            host=config_get("REDIS_HOST"),
            port=config_get("REDIS_PORT"),
            password=config_get("REDIS_PASSWORD")
        )
        # Dumb check to make sure we have a connection or we have to stop.
        r.info()
    except redis.exceptions.ConnectionError:
        raise StorageException()

    return r


def username_characters_check(form, field):
    """Does the username match our regex?"""
    if not VALID_USERNAME.fullmatch(field.data):
        raise ValidationError("Provided username is not valid.")


def username_duplicates_check(form, field):
    """Check if we already have the same username registered."""
    try:
        db = get_db_connection()
        if db.exists(DB_KEY_FORMAT.format(field.data)):
            raise ValidationError("Provided username is already in use.")
    except StorageException:
        abort(500)


def sshkey_valid_check(form, field):
    """Check the validity of an ssh key uploaded.

    Make sure the ssh-keygen can make something out of the key.
    ssh-keygen returns 0 if everything is ok, 255 otherwise.
    """
    with tempfile.NamedTemporaryFile() as pub_ssh, open(os.devnull) as null:
        pub_ssh.write(bytes(field.data.strip() + "\n", "utf-8"))
        pub_ssh.flush()

        try:
            subprocess.check_call(
                ["ssh-keygen", "-l", "-f", pub_ssh.name],
                stdout=null, stderr=null)
        except subprocess.CalledProcessError as ex:
            print(ex.returncode)
            raise ValidationError("Provided SSH key is not valid.")


class SignUpForm(Form):
    """Simple form to upload SSH keys and choose the username."""

    name_len = "Provided username length is not valid (3 <= length <= 32)."
    username = StringField(
        id="username",
        label="Username",
        description="The username to use with the system",
        render_kw={
            "aria-describedby": "usernameHelp",
            "placeholder": "Choose a username."
        },
        validators=[
            InputRequired(message="A username is required."),
            Length(min=3, max=32, message=name_len),
            NoneOf(
                config_get("INVALID_USERNAMES"),
                message="Provided username is not valid."),
            username_characters_check,
            username_duplicates_check
        ]
    )
    ssh_key = TextAreaField(
        id="sshkey",
        label="SSH Key",
        description="Your public SSH key",
        render_kw={
            "autocomplete": "off",
            "rows": 10,
            "aria-describedby": "sshkeyHelp",
            "placeholder": "Copy and paste your public SSH key."
        },
        validators=[
            InputRequired(message="An SSH key is required."),
            sshkey_valid_check
        ]
    )


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
        website_name=WEBSITE_NAME,
        description=config_get("DESCRIPTION"),
        version=__versionfull__
    )


@app.errorhandler(404)
def page_not_found(error):
    """Render 404 errors."""
    return render_template(
        "404.html",
        page_title="{:s} - {:s}".format(PAGE_TITLE, "Resource Not Found"),
        body_title="Resource not found"
    ), 404


@app.errorhandler(500)
def internal_server_error(error):
    """Render 500 errors."""
    return render_template(
        "500.html",
        page_title="{:s} - {:s}".format(PAGE_TITLE, "Internal Error"),
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

    page_title = "{:s} - {:s}".format(PAGE_TITLE, "Home Page")

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

    o_path = path
    t_path = os.path.join(ROOT, path)

    if path[0] != "/":
        path = "/{}".format(path)
    if o_path[-1] != "/":
        o_path = "{}/".format(o_path)

    if os.path.isdir(t_path):
        parent = os.path.dirname(path)
        if parent == "/":
            parent = None

        body_title = "Index of &#171;{}&#187;".format(o_path)
        page_title = "{} - {}".format(PAGE_TITLE, body_title)

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


@app.route("/signup/", methods=["GET", "POST"])
def signup():
    """The signup page and its form."""
    form = SignUpForm()
    if form.validate_on_submit():
        username = form.username.data
        ssh_key = form.ssh_key.data
        try:
            r_key = DB_KEY_FORMAT.format(username)
            db = get_db_connection()
            r_map = {
                "username": username,
                "ssh_key": ssh_key,
                "registered_on": datetime.datetime.utcnow()
            }
            db.hmset(r_key, r_map)
            db.publish(REDIS_PUB_CH, r_key)
        except StorageException:
            abort(500)

        page_title = "{} - {}".format(PAGE_TITLE, "Ready to Go!")
        return render_template(
            "signedup.html",
            ssh_key=ssh_key, username=username, page_title=page_title)

    page_title = "{} - {}".format(PAGE_TITLE, "Sign Up")
    return render_template("signup.html", form=form, page_title=page_title)
