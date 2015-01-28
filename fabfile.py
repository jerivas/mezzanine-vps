from __future__ import print_function, unicode_literals
from future.builtins import input, open

import os
import re
import sys
from functools import wraps
from getpass import getpass, getuser
from contextlib import contextmanager
from posixpath import join

from fabric.api import abort, env, cd, prefix, sudo as _sudo, run as _run, hide, task, local
from fabric.contrib.console import confirm
from fabric.contrib.files import exists, upload_template
from fabric.contrib.project import rsync_project
from fabric.colors import yellow, green, blue, red

################
# Config setup #
################

conf = {}
if sys.argv[0].split(os.sep)[-1] in ("fab",             # POSIX
                                     "fab-script.py"):  # Windows
    # Ensure we import settings from the current dir
    try:
        conf = __import__("settings", globals(), locals(), [], 0).FABRIC
        try:
            conf["HOSTS"][0]
        except (KeyError, ValueError):
            raise ImportError
    except (ImportError, AttributeError):
        print("Aborting, no hosts defined.")
        exit()

env.user = conf.get("SSH_USER", getuser())
env.password = conf.get("SSH_PASS", "")
env.key_filename = conf.get("SSH_KEY_PATH", None)
env.hosts = conf.get("HOSTS", [])
env.domains = conf.get("DOMAINS", [conf.get("LIVE_HOSTNAME", env.hosts[0])])
env.domains_nginx = " ".join(env.domains)
env.domains_regex = "|".join(env.domains)
env.domains_python = ", ".join(["'%s'" % s for s in env.domains])

env.proj_name = conf.get("PROJECT_NAME", os.getcwd().split(os.sep)[-1])
env.proj_path = "/home/%s/mezzanine/%s" % (env.user, env.proj_name)
env.venv_home = conf.get("VIRTUALENV_HOME", "/home/%s/.virtualenvs" % env.user)
env.venv_name = conf.get("VIRTUALENV_NAME", env.proj_name)
env.venv_path = "%s/%s" % (env.venv_home, env.venv_name)
env.reqs_path = conf.get("REQUIREMENTS_PATH", "requirements/project.txt")
env.manage = "%s/bin/python %s/manage.py" % (env.venv_path, env.proj_path)
env.deploy_tool = conf.get("DEPLOY_TOOL", "rsync")
env.repo_path = "/home/%s/git/%s.git" % (env.user, env.proj_name)
env.locale = conf.get("LOCALE", "en_US.UTF-8")
env.supervisor_conf = "/home/%s/etc/supervisor/conf.d/%s.conf" % (
    env.user, env.proj_name)

env.admin_pass = conf.get("ADMIN_PASS", None)
env.db_pass = conf.get("DB_PASS", None)
env.ssl_disabled = "#"
env.secret_key = conf.get("SECRET_KEY", "")
env.nevercache_key = conf.get("NEVERCACHE_KEY", "")


##################
# Template setup #
##################

# Each template gets uploaded at deploy time, only if their
# contents has changed, in which case, the reload command is
# also run.

templates = {
    "nginx": {
        "local_path": "deploy/nginx.conf",
        "remote_path": "/etc/nginx/sites-enabled/%(proj_name)s.conf",
        "reload_command": "service nginx restart",
    },
    "gunicorn": {
        "local_path": "deploy/gunicorn.conf.py.template",
        "remote_path": "%(proj_path)s/gunicorn.conf.py",
    },
    "supervisorctl": {
        "local_path": "deploy/supervisorctl.conf",
        "remote_path": "%(supervisor_conf)s",
        "reload_command": "supervisorctl restart gunicorn_%(proj_name)s",
    },
    "settings": {
        "local_path": "deploy/local_settings.py.template",
        "remote_path": "%(proj_path)s/local_settings.py",
    },
    "post receive hook": {
        "local_path": "deploy/post-receive",
        "remote_path": "%(repo_path)s/hooks/post-receive",
        "mode": "+x",
        "render_if": env.deploy_tool == "git",
    },
    "cron": {
        "local_path": "deploy/crontab",
        "remote_path": "/etc/cron.d/%(proj_name)s",
        "owner": "root",
        "mode": "600",
    }
}


######################################
# Context for virtualenv and project #
######################################

@contextmanager
def virtualenv():
    """Run commands within the project's virtualenv."""
    with cd(env.venv_path):
        with prefix("source %s/bin/activate" % env.venv_path):
            yield


@contextmanager
def project():
    """Run commands within the project's directory."""
    with virtualenv():
        with cd(env.proj_path):
            yield


@contextmanager
def update_changed_requirements():
    """
    Check for changes in the requirements file across an update,
    and get new requirements if changes have occurred.
    """
    reqs_path = join(env.proj_path, env.reqs_path)
    get_reqs = lambda: run("cat %s" % reqs_path)
    old_reqs = get_reqs() if env.reqs_path else ""
    yield
    if old_reqs:
        new_reqs = get_reqs()
        if old_reqs == new_reqs:
            # Unpinned requirements should always be checked.
            for req in new_reqs.split("\n"):
                if req.startswith("-e"):
                    if "@" not in req:
                        # Editable requirement without pinned commit.
                        break
                elif req.strip() and not req.startswith("#"):
                    if not set(">=<") & set(req):
                        # PyPI requirement without version.
                        break
            else:
                # All requirements are pinned.
                return
        pip("-r %s/%s" % (env.proj_path, env.reqs_path))


###########################################
# Utils and wrappers for various commands #
###########################################

def _print(output):
    print()
    print(output)
    print()


def print_command(command):
    _print(blue("$ ", bold=True) +
           yellow(command, bold=True) +
           red(" ->", bold=True))


@task
def run(command, show=True, *args, **kwargs):
    """
    Runs a shell comand on the remote server.
    """
    if show:
        print_command(command)
    with hide("running"):
        return _run(command, *args, **kwargs)


@task
def sudo(command, show=True, *args, **kwargs):
    """
    Runs a command as sudo.
    """
    if show:
        print_command(command)
    with hide("running"):
        return _sudo(command, *args, **kwargs)


def log_call(func):
    @wraps(func)
    def logged(*args, **kawrgs):
        header = "-" * len(func.__name__)
        _print(green("\n".join([header, func.__name__, header]), bold=True))
        return func(*args, **kawrgs)
    return logged


def get_templates():
    """
    Returns each of the templates with env vars injected if they pass their own
    render_if check.
    """
    injected = {}
    for name, data in templates.items():
        if data.get("render_if", True):
            try:
                del data["render_if"]
            except KeyError:
                pass
            injected[name] = dict([(k, v % env) for k, v in data.items()])
    return injected


def upload_template_and_reload(name):
    """
    Uploads a template only if it has changed, and if so, reload a
    related service.
    """
    template = get_templates()[name]
    local_path = template["local_path"]
    if not os.path.exists(local_path):
        project_root = os.path.dirname(os.path.abspath(__file__))
        local_path = os.path.join(project_root, local_path)
    remote_path = template["remote_path"]
    reload_command = template.get("reload_command")
    owner = template.get("owner")
    mode = template.get("mode")
    remote_data = ""
    if exists(remote_path):
        with hide("stdout"):
            remote_data = sudo("cat %s" % remote_path, show=False)
    with open(local_path, "r") as f:
        local_data = f.read()
        # Escape all non-string-formatting-placeholder occurrences of '%':
        local_data = re.sub(r"%(?!\(\w+\)s)", "%%", local_data)
        if "%(db_pass)s" in local_data:
            env.db_pass = db_pass()
        local_data %= env
    clean = lambda s: s.replace("\n", "").replace("\r", "").strip()
    if clean(remote_data) == clean(local_data):
        return
    upload_template(local_path, remote_path, env, use_sudo=True, backup=False)
    if owner:
        sudo("chown %s %s" % (owner, remote_path))
    if mode:
        sudo("chmod %s %s" % (mode, remote_path))
    if reload_command:
        sudo(reload_command)


def db_pass():
    """Prompt for the database password if unknown."""
    if not env.db_pass:
        env.db_pass = getpass("Enter the database password: ")
    return env.db_pass


@task
def apt(packages):
    """
    Installs one or more system packages via apt.
    """
    return sudo("apt-get install -y -q " + packages)


@task
def pip(packages):
    """Install Python packages within the virtual environment."""
    with virtualenv():
        return run("pip install %s" % packages)


def postgres(command):
    """
    Runs the given command as the postgres user.
    """
    show = not command.startswith("psql")
    return sudo(command, show=show, user="postgres")


@task
def psql(sql, show=True):
    """
    Runs SQL against the project's database.
    """
    out = postgres('psql -c "%s"' % sql)
    if show:
        print_command(sql)
    return out


@task
def backup(filename):
    """
    Backs up the database.
    """
    return postgres("pg_dump -Fc %s > %s" % (env.proj_name, filename))


@task
def restore(filename):
    """
    Restores the database.
    """
    return postgres("pg_restore -c -d %s %s" % (env.proj_name, filename))


@task
def python(code, show=True):
    """
    Runs Python code in the project's virtual environment, with Django loaded.
    """
    setup = "import os; os.environ[\'DJANGO_SETTINGS_MODULE\']=\'settings\';"
    full_code = 'python -c "%s%s"' % (setup, code.replace("`", "\\\`"))
    with project():
        result = run(full_code, show=False)
        if show:
            print_command(code)
    return result


def static():
    """
    Returns the live STATIC_ROOT directory.
    """
    return python("from django.conf import settings;"
                  "print settings.STATIC_ROOT", show=False).split("\n")[-1]


@task
def manage(command):
    """
    Runs a Django management command.
    """
    return run("%s %s" % (env.manage, command))


#########################
# Install and configure #
#########################

@task
@log_call
def install():
    """
    Installs the base system and Python requirements for the entire server.
    """
    locale = "LC_ALL=%s" % env.locale
    with hide("stdout"):
        if locale not in sudo("cat /etc/default/locale"):
            sudo("update-locale %s" % locale)
            run("exit")
    sudo("apt-get update -y -q >> /dev/null")
    apt("nginx libjpeg-dev python-dev python-setuptools git-core "
        "postgresql libpq-dev memcached supervisor python-pip")
    sudo("pip install virtualenv virtualenvwrapper")
    run("mkdir -p /home/%s/{tmp,logs,etc}" % env.user)
    run("mkdir -p /home/%s/etc/supervisor/conf.d" % env.user)
    upload_template("deploy/supervisord.conf",
                    "/home/%s/etc/supervisord.conf" % env.user, env)
    run("supervisord -c /home/%s/etc/supervisord.conf" % env.user)
    run("mkdir -p %s" % env.venv_home)
    run("echo 'export WORKON_HOME=%s' >> /home/%s/.bashrc" % (env.venv_home,
                                                              env.user))
    run("echo 'source /usr/local/bin/virtualenvwrapper.sh' >> "
        "/home/%s/.bashrc" % env.user)
    print("Successfully set up git, pip, virtualenv, supervisor, and "
          "memcached.")


@task
@log_call
def create():
    """
    Set up a new virtualenv or reuse an existing one. Create DB and DB user.
    Set up Git. Configure SSL. Set up supervisor and gunicorn.
    """
    # Create project path
    run("mkdir -p %s" % env.proj_path)

    # Set up virtual env
    run("mkdir -p %s" % env.venv_home)
    with cd(env.venv_home):
        if exists(env.venv_name):
            if confirm("Virtualenv already exists: %s. Reinstall?"
                       % env.venv_name):
                print("Reinstalling virtualenv from scratch.")
                run("rm -r %s" % env.venv_name)
                run("virtualenv %s" % env.venv_name)
            else:
                print("Using existing virtualenv: %s." % env.venv_name)
        else:
            if confirm("Virtualenv does not exist: %s. Create?"
                       % env.venv_name):
                print("Creating virtualenv.")
                run("virtualenv %s" % env.venv_name)
                print("New virtualenv: %s." % env.venv_path)
            else:
                abort("Aborting at user request.")
        # Make sure we don't inherit anything from the system's Python
        run("touch %s/lib/python2.7/sitecustomize.py" % env.venv_name)

    # Set up Git if selected as deployment tool
    if env.deploy_tool == "git":
        if not exists(env.repo_path):
            print("Setting up git repo")
            run("mkdir -p %s" % env.repo_path)
            with cd(env.repo_path):
                run("git init --bare")
        upload_template_and_reload("post receive hook")
        print("Git repo ready at %s" % env.repo_path)
        local("git remote add production ssh://%s@%s%s" % (env.user,
              env.host_string, env.repo_path))
        print("Added new remote 'production'. You can now push to it with "
              "git push production.")
        print("Pushing master branch.")
        local("git push production +master:refs/heads/master")
    # If not using git, upload files using rsync instead
    else:
        print("Uploading all files to server")
        rsync_project(remote_dir=env.proj_path, local_dir=os.getcwd() + os.sep,
                      exclude=".git", extra_opts="--exclude-from=.gitignore")
    print("All files pushed to remote server.")

    # Create DB and DB user.
    pw = db_pass()
    user_sql_args = (env.proj_name, pw.replace("'", "\'"))
    user_sql = "CREATE USER %s WITH ENCRYPTED PASSWORD '%s';" % user_sql_args
    psql(user_sql, show=False)
    shadowed = "*" * len(pw)
    print_command(user_sql.replace("'%s'" % pw, "'%s'" % shadowed))
    psql("CREATE DATABASE %s WITH OWNER %s ENCODING = 'UTF8' "
         "LC_CTYPE = '%s' LC_COLLATE = '%s' TEMPLATE template0;" %
         (env.proj_name, env.proj_name, env.locale, env.locale))

    # Set up SSL certificate
    # if not env.ssl_disabled:
    #     conf_path = "/etc/nginx/conf"
    #     if not exists(conf_path):
    #         sudo("mkdir %s" % conf_path)
    #     with cd(conf_path):
    #         crt_file = env.proj_name + ".crt"
    #         key_file = env.proj_name + ".key"
    #         if not exists(crt_file) and not exists(key_file):
    #             try:
    #                 crt_local, = glob(join("deploy", "*.crt"))
    #                 key_local, = glob(join("deploy", "*.key"))
    #             except ValueError:
    #                 parts = (crt_file, key_file, env.domains[0])
    #                 sudo("openssl req -new -x509 -nodes -out %s -keyout %s "
    #                      "-subj '/CN=%s' -days 3650" % parts)
    #             else:
    #                 upload_template(crt_local, crt_file, use_sudo=True)
    #                 upload_template(key_local, key_file, use_sudo=True)

    # Set up project.
    upload_template_and_reload("settings")
    with project():
        if env.reqs_path:
            pip("-r %s/%s" % (env.proj_path, env.reqs_path))
        pip("gunicorn setproctitle south psycopg2 "
            "django-compressor python-memcached")
        manage("createdb --noinput --nodata")
        python("from django.conf import settings;"
               "from django.contrib.sites.models import Site;"
               "Site.objects.filter(id=settings.SITE_ID).update(domain='%s');"
               % env.domains[0])
        for domain in env.domains:
            python("from django.contrib.sites.models import Site;"
                   "Site.objects.get_or_create(domain='%s');" % domain)
        if env.admin_pass:
            pw = env.admin_pass
            user_py = ("from mezzanine.utils.models import get_user_model;"
                       "User = get_user_model();"
                       "u, _ = User.objects.get_or_create(username='admin');"
                       "u.is_staff = u.is_superuser = True;"
                       "u.set_password('%s');"
                       "u.save();" % pw)
            python(user_py, show=False)
            shadowed = "*" * len(pw)
            print_command(user_py.replace("'%s'" % pw, "'%s'" % shadowed))

    return True


@task
@log_call
def remove(venv=False):
    """
    Blow away the current project.
    """
    if venv and exists(env.venv_path):
        run("rm -rf %s" % env.venv_path)
        print("Removed remote virtualenv: %s." % env.venv_name)
    if exists(env.repo_path):
        run("rm -rf %s" % env.repo_path)
        local("git remote rm production", capture=True)
        print("Removed remote git repo: %s." % env.repo_path)
    for template in get_templates().values():
        remote_path = template["remote_path"]
        if exists(remote_path):
            sudo("rm %s" % remote_path)
            print("Removed remote file: %s." % template["remote_path"])
    if exists(env.proj_path):
        run("rm -rf %s" % env.proj_path)
    psql("DROP DATABASE IF EXISTS %s;" % env.proj_name)
    psql("DROP USER IF EXISTS %s;" % env.proj_name)
    run("supervisorctl update")


##############
# Deployment #
##############

@task
@log_call
def restart():
    """
    Restart gunicorn worker processes for the project.
    """
    pid_path = "%s/gunicorn.pid" % env.proj_path
    if exists(pid_path):
        run("kill -HUP `cat %s`" % pid_path)
    else:
        run("supervisorctl restart gunicorn_%s" % env.proj_name)


@task
@log_call
def deploy(first=False, backup=False):
    """
    Deploy latest version of the project.
    Check out the latest version of the project from version
    control, install new requirements, sync and migrate the database,
    collect any new static assets, and restart gunicorn's work
    processes for the project.
    """
    if not exists(env.proj_path):
        abort("Project %s does not exist in host server. "
              "Run fab create before trying to deploy." % env.proj_name)
    for name in get_templates():
        upload_template_and_reload(name)
    update_changed_requirements()
    if env.deploy_tool == "git":
        local("git push production master")
    else:
        rsync_project(remote_dir=env.proj_path, local_dir=os.getcwd() + os.sep,
                      exclude=".git", extra_opts="--exclude-from=.gitignore")
    if backup:
        with project():
            backup("last.db")
            static_dir = static()
            if exists(static_dir):
                run("tar -cf last.tar %s" % static_dir)
    manage("collectstatic -v 0 --noinput")
    manage("syncdb --noinput")
    manage("migrate --noinput")
    if first:
        run("supervisorctl update")
    else:
        restart()
    return True


@task
@log_call
def rollback():
    """
    Reverts project state to the last deploy.
    When a deploy is performed, the current state of the project is
    backed up. This includes the last commit checked out, the database,
    and all static files. Calling rollback will revert all of these to
    their state prior to the last deploy.
    """
    with project():
        with update_changed_requirements():
            update = "git checkout"
            run("%s `cat last.commit`" % update)
        with cd(join(static(), "..")):
            run("tar -xf %s" % join(env.proj_path, "last.tar"))
        restore("last.db")
    restart()


@task
@log_call
def all():
    """
    Installs everything required on a new system and deploy.
    From the base software, up to the deployed project.
    """
    if create():
        deploy(first=True)
