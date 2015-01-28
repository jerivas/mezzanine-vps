# Mezzanine VPS

Fabric files and related resources for deploying multiple [Mezzanine](http://mezzanine.jupo.org) sites to a VPS.

## Overview

This implementation is based on the resources included by default with Mezzanine, but with some important changes:

- Vanilla `gunicorn` is used instead of the the deprecated `gunicorn_django`.
- You don't need to host your repos in external sites (GitHub, Bitbucket). The contents are transferred directly from your dev machine to the server.
- You can upload files to the server via rsync instead of git (in case your project is not under VCS).
- You don't need to know which port Gunicorn is going to use, because the connection from Nginx is to a socket file.
- Operations using sudo only require you to type the password once.
- Invalid requests (hosts other than `ALLOWED_HOSTS`) are blocked on Nginx level.
- Static files are set to expire after 30 days in browser cache.

There's one thing I haven't been able to test: SSL certificates. As of now **all portions related to SSL have been commented out**.

## Pre-requisites

**In your dev machine**
- Mezzanine
- Django
- Fabric
- A git repo with your project files (if you want to deploy with git)
- A pip requirements file

**In your VPS**
- pip
- virtualenv
- supervisor
- git
- memcached

*Note: this script can install the server pre-requisites for you.*

## Installation

Download `fabfile.py`, `fabsettings.py`, `wsgi.py` and `deploy/` to your Mezzanine project folder, replacing them if they already exist.

## Usage

This section explains the process of deploying a site from the moment you purchase your VPS until the site is up and running:

1. Login as root to your spanking new VPS.
1. Complete some basic security-related steps. At least you should update all your system packages and disable root login via SSH. You'll find a little script in this repo, `vps_primer.sh`, which can do these things for you. Simply download it to your VPS, make it executable, and run `./vps_primer.sh new_user`. From now on you should login to your VPS as `new_user` and use that user for your deployment tasks. More instructions included with the script.
1. In your dev machine, copy the contents of `fabsettings.py` to `local_settings.py` and tweak to your liking. This is the only file you have to edit, all others will be populated by Fabric. All available settings are explained in `fabsettings.py`. **These settings are different from those provided in `settings.py` by Mezzanine, so make sure you only use the ones provided by `fabsettings.py`.**
1. Run `fab install` to prepare your server for hosting your projects.
1. Run `fab all` to setup everything for your project in the server. `fab all` simply calls `fab create` and the `fab deploy:first=True`. It basically sets up your project environment and then deploys it for the first time.
1. Subsequent deployments can be done with `fab deploy`. If you use `fab deploy:backup=True`, Fabric will backup your project database and static files before deploying the current version of the project.
1. If you want to wipe out all traces of the project in your server: `fab remove`. Calling `fab remove:venv=True` will also delete the virtualenv associated to the project.
1. Get a list of all available tasks with `fab --list`.

All the steps are only necessary for the first site being deployed to the VPS. Subsequent sites can skip steps 1, 2, and 4.

## Minimal settings

You don't need to fill in all the settings in `fabsettings.py`. Most of the time, I deploy with no issue using these settings:

```python
# local_settings.py in dev machine
# ...

ALLOWED_HOSTS = ["www.example.com"]
FABRIC = {
	"DEPLOY_TOOL": "git",
    "SSH_USER": "vps_user",
    "HOSTS": "vps_ip_address",
    "DOMAINS": ALLOWED_HOSTS,
    "REQUIREMENTS_PATH": "requirements.txt",
    "DB_PASS": "pass_for_db",
    "SECRET_KEY": SECRET_KEY,
    "NEVERCACHE_KEY": NEVERCACHE_KEY,
}

#...
```

## Support

I've tested the fabfile with the following stack:

- Django 1.5, 1.6
- Mezzanine 3.x
- Ubuntu 14.04 dev machine
- Ubuntu 12.04 and 14.04 server

## Known issues / TODO

- No Mercurial, SVN support
- No MySQL support
- SSL support not tested
