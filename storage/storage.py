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
    redirect,
    render_template
)

from werkzeug.contrib.cache import (
    RedisCache,
    SimpleCache
)

import boto3
import botocore
import math
import os
import sys

__version__ = "2016.4"
__versionfull__ = __version__

# pylint: disable=invalid-name
app = Flask("kernelci-storage")
app.config.from_object("settings")

settings_var = os.environ.get("STORAGE_SETTINGS")
if settings_var:
    app.config.from_pyfile(settings_var, silent=True)

config_get = app.config.get

cache = None
if config_get("REDIS_CACHE"):
    cache = RedisCache(
        host=config_get("REDIS_HOST"),
        port=config_get("REDIS_PORT"),
        password=config_get("REDIS_PASSWORD"),
        db=config_get("REDIS_DB"),
        default_timeout=config_get("REDIS_TIMEOUT"),
        key_prefix=config_get("REDIS_PREFIX")
    )
else:
    cache = SimpleCache(threshold=50)

# The AWS session to connect to services.
aws_session = None
if all([config_get("AWS_ACCESS_KEY_ID"), config_get("AWS_SECRET_ACCESS_KEY")]):
    aws_session = boto3.session.Session()
else:
    app.logger.error("No AWS credentials specified")
    sys.exit(1)

s3_client = aws_session.client("s3")

# List of available size for bytes formatting.
SIZES = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']
WEBSITE_NAME = config_get("WEBSITE_NAME")


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


def scan_bucket(directory):
    """Scan an S3 bucket looking for the provided "directory".

    :param directory: The path to look up in the bucket.
    :type directory: str
    :return Yield the found values, or 404 if nothing is found.
    """
    objects = s3_client.list_objects(
        Bucket=config_get("AWS_S3_BUCKET"),
        Delimiter="/",
        Prefix=directory
    )

    # Get the directories, and then the files.
    entries = objects.get("CommonPrefixes", [])
    entries.extend(objects.get("Contents", []))

    # If S3 hasn't anything in a "directory", it means it doesn't exists.
    if not entries:
        abort(404)

    for entry in entries:
        name = None
        values = {}

        if entry.get("Prefix", None):
            path = entry["Prefix"]

            if path[0] != "/":
                path = "/{:s}".format(path)

            name = os.path.basename(path[:-1])
            values["path"] = path
            values["size"] = None
            values["bytes"] = None
            values["time"] = None
            values["time_iso"] = None
            values["time_sort"] = -1
            values["sort"] = "d{:s}".format(name.lower())
            values["type"] = "dir"
        elif entry.get("Key", None):
            path = entry["Key"]

            if path[0] != "/":
                path = "/{:s}".format(path)

            name = os.path.basename(path)
            time = entry["LastModified"]
            values["path"] = path
            values["size"] = size_format(entry["Size"])
            values["bytes"] = entry["Size"]
            values["time"] = "{} {}".format(time.date(), time.time())
            values["time_iso"] = time.isoformat()
            values["time_sort"] = time.timestamp()
            values["sort"] = "f{:s}".format(name.lower())
            values["type"] = "file"

        yield name, values


def generate_artifact_url(key):
    """Generate the URL of an object in the bucket.

    If the key is not found, return 404.

    :param key: The key to check in the bucket.
    :type key: str
    :return The actual URL of the object.
    :rtype str
    """
    bucket = config_get("AWS_S3_BUCKET")
    try:
        # First check if the key exists.
        s3_client.head_object(Bucket=bucket, Key=key)
        return s3_client.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": bucket,
                "Key": key
            }
        )
    except botocore.exceptions.ClientError:
        abort(404)


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


@app.route("/", defaults={"path": "/"}, methods=["GET"])
@app.route("/<path:path>", methods=["GET"])
def index(path):
    """The only needed route/view."""

    # Dummy logic: if it ends with a slash, it's a dir.
    if any([path == "/", path[-1] == "/"]):
        rendered = cache.get(path)

        if not rendered:
            if path == "/":
                page_title = "{:s} - {:s}".format(WEBSITE_NAME, "Home Page")
                body_title = "Home Page"
                parent = None
                path = ""
            else:
                page_title = "{:s} - {:s}".format(
                    WEBSITE_NAME, "Index of {:s}".format(path))
                body_title = "Index of &#171;{:s}&#187;".format(path)
                parent = os.path.split(path[:-1])[0]

                if not parent:
                    parent = "/"
                else:
                    if parent[0] != "/":
                        parent = "/{:s}".format(parent)
                    if parent[-1] != "/":
                        parent = "{:s}/".format(parent)

            rendered = render_template(
                "listing.html",
                entries=scan_bucket(path),
                page_title=page_title,
                body_title=body_title,
                parent=parent
            )

            cache.set(path, rendered)

        return rendered
    else:
        return redirect(generate_artifact_url(path))


if __name__ == "__main__":
    app.run(debug=config_get("DEBUG"))
