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

# Run in debug mode.
DEBUG = True
TESTING = DEBUG

# Used for the Server response header.
SERVER_HEADER = "Storage"

# Name of the website
WEBSITE_NAME = "Storage"

# Description that will be used in the meta tags.
DESCRIPTION = "Storage"

# AWS access id and key.
AWS_ACCESS_KEY_ID = None
AWS_SECRET_ACCESS_KEY = None

# S3 bucket name.
AWS_S3_BUCKET = None

# Redis cache.
REDIS_CACHE = False
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_PASSWORD = None
REDIS_PREFIX = "kcistorage|"
REDIS_TIMEOUT = 300
