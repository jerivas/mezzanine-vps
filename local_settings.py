# Copy these settings to your own local_setting.py

# Add the domain(s) you want to deploy Mezzanine to.
# Used for security in both Django and Nginx.
ALLOWED_HOSTS = ["www.example.com"]

# Comment out the settings where you want to use defaults.
FABRIC = {
    # VPS SSH username.
    # Default: your user in the dev machine.¡
    "SSH_USER": "",
    # VPS SSH password (consider using key-based auth).
    "SSH_PASS": "",
    # Local path to SSH key file, for key-based auth.
    "SSH_KEY_PATH": "",
    # The IP address of your VPS.
    "HOSTS": "",
    # Live domain(s)
    # Better edit this one in ALLOWED HOSTS.
    "DOMAINS": ALLOWED_HOSTS,
    # Unique identifier for project.
    # Default: container folder name.
    "PROJECT_NAME": "",
    # Absolute remote path for virtualenvs.
    # Default: ~/.virtualenvs
    "VIRTUALENV_HOME": "",
    # Name of the remote virtualenv to use.
    # Default: PROJECT_NAME
    "VIRTUALENV_NAME": "",
    # Path to pip requirements, relative to project.
    # Default: requirements/project.txt
    "REQUIREMENTS_PATH": "",
    # Locale for your live project. Should end with ".UTF-8"
    # Default: en_US.UTF-8
    "LOCALE": "",
    # Live database password
    "DB_PASS": "",
    # Live admin user password (optional)
    "ADMIN_PASS": "",
    # Make sure these keys are available in local_settings.py.
    "SECRET_KEY": SECRET_KEY,
    "NEVERCACHE_KEY": NEVERCACHE_KEY,
}
