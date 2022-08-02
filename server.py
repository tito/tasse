import os
from pytz import utc
from loguru import logger
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from flask import Flask, jsonify
from datetime import datetime
from ruamel.yaml import YAML
import shlex
import subprocess
import sys
import logging


# -----------------------------------------------------------------------
# Redirect standard logging to loguru
# -----------------------------------------------------------------------

class InterceptHandler(logging.Handler):
    def emit(self, record):
        # Get corresponding Loguru level if it exists.
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message.
        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage())

logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
loguru_handlers = {}


# -----------------------------------------------------------------------
# Path configuration
# -----------------------------------------------------------------------

curdir = os.path.realpath(os.path.dirname(__file__))
datadir = os.path.join(curdir, "data")
tasksdir = os.path.join(datadir, "tasks")
os.chdir(datadir)


# -----------------------------------------------------------------------
# APS Scheduler configuration
# -----------------------------------------------------------------------

jobstores = {
    "default": SQLAlchemyJobStore(
        url=f"sqlite:///jobs.sqlite")
}
executors = {
    "default": ThreadPoolExecutor(5)
}
job_defaults = {
    "coalesce": False,
    "max_instances": 3
}

scheduler = BackgroundScheduler(
    jobstores=jobstores,
    executors=executors,
    job_defaults=job_defaults,
    timezone=utc)

app = Flask(__name__)


# -----------------------------------------------------------------------
# Tasks management
# -----------------------------------------------------------------------

def execute_and_log(clogger, cmd, taskdir, env):
    clogger.debug(f"[Run {' '.join(cmd)}]")
    process = subprocess.Popen(
        cmd, cwd=taskdir, env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT)
    while True:
        line = process.stdout.readline()
        if not line:
            break
        clogger.info(line.decode("utf8").strip())
    process.wait()
    return process


def execute_task(taskname, metadata):
    clogger = logger.bind(taskname=taskname)
    taskdir = os.path.join(tasksdir, taskname)

    entrypoint = metadata.get("entrypoint")
    if not entrypoint:
        # autodetection ?
        for ext in ("py", "sh"):
            entrypoint = f"task.{ext}"
            if os.path.exists(os.path.join(taskdir, entrypoint)):
                break
        else:
            raise Exception("No entrypoint found")

    taskfile = os.path.join(taskdir, entrypoint)
    clogger.info(f">>> Task {taskname}/{entrypoint}")

    env = os.environ.copy()
    env.pop("POETRY_ACTIVE", None)
    env.pop("VIRTUAL_ENV", None)
    have_requirements = False
    have_poetry = True

    # detect requirements.txt
    requirements_txt = os.path.join(taskdir, "requirements.txt")
    if os.path.exists(requirements_txt):
        have_requirements = True
        venv_directory = os.path.join(datadir, "venvs", taskname)
        env["VIRTUAL_ENV"] = os.path.realpath(venv_directory)
        cmd = shlex.split(f"virtualenv {venv_directory}")
        execute_and_log(clogger, cmd, taskdir, env)
        venv_ppip = os.path.join(env["VIRTUAL_ENV"], "bin", "pip")
        cmd = shlex.split(f"{venv_ppip} install -r {requirements_txt}")
        execute_and_log(clogger, cmd, taskdir, env)

    # detect poetry
    elif os.path.exists(os.path.join(taskdir, "pyproject.toml")):
        env["POETRY_VIRTUALENVS_PATH"] = os.path.join(datadir, "venvs")
        cmd = shlex.split(f"poetry install")
        clogger.debug(f"Prepare: {cmd} in {taskdir}")
        execute_and_log(clogger, cmd, taskdir, env)
        have_poetry = True

    # execute
    if entrypoint.endswith(".py"):
        if have_requirements:
            venv_python = os.path.join(env["VIRTUAL_ENV"], "bin", "python")
            cmd = shlex.split(f"{venv_python} {taskfile}")
        elif have_poetry:
            cmd = shlex.split(f"poetry run python {taskfile}")
        else:
            cmd = shlex.split(f"python {taskfile}")

    elif entrypoint.endswith(".sh"):
        cmd = shlex.split(f"bash -x {taskfile}")

    logger.debug(f"Run: {cmd} in {taskdir}")
    process = execute_and_log(clogger, cmd, taskdir, env)
    clogger.info(
        f"<<< Task {taskname}/{entrypoint} ended "
        f"with status code {process.returncode}")
    clogger.complete()


def get_task_id(taskname):
    return f"tasks:{taskname}"


def is_task_id(taskname):
    return taskname.startswith("tasks:")


def ensure_task(taskname, jobdir):
    with open(os.path.join(jobdir, "task.yaml"), encoding="utf8") as fd:
        yaml = YAML(typ="safe")
        metadata = yaml.load(fd)

    options = metadata["scheduler"]
    if "trigger" not in options:
        raise Exception("task.yaml requires scheduler.trigger")
    taskid = get_task_id(taskname)
    job = scheduler.get_job(taskid)
    modified = False
    if job and job.kwargs["metadata"] != metadata:
        logger.info(f"Job modified: {taskname} with {options}")
        job.remove()
        job = None
        modified = True
    if not job:
        if not modified:
            logger.info(f"Job detected: {taskname} with {options}")
            handler_id = logger.add(
                os.path.join(
                    datadir, "logs", taskname, f"log.txt"),
                format="{time} | {message}",
                rotation="50MB",
                retention="15 days",
                enqueue=True,
                filter=lambda record: record["extra"].get(
                    "taskname") == taskname,
            )
            loguru_handlers[taskname] = handler_id
        scheduler.add_job(
            execute_task,
            id=taskid,
            name=taskname,
            replace_existing=True,
            max_instances=1,
            kwargs={"taskname": taskname, "metadata": metadata},
            **options)


def scan_directories():
    current_jobs = []
    for taskname in os.listdir(tasksdir):
        jobdir = os.path.join(tasksdir, taskname)
        if not os.path.isdir(jobdir):
            continue
        try:
            ensure_task(taskname, jobdir)
            current_jobs.append(taskname)
        except Exception:
            logger.exception(f"Unable to load job {taskname}")

    # remove tasks that has been removed from the directory
    for job in scheduler.get_jobs():
        if not job.name:
            continue
        if not is_task_id(job.id):
            continue
        if job.name not in current_jobs:
            logger.warning(f"Job removed: {job.name}")
            scheduler.remove_job(get_task_id(job.name))
            handler_id = loguru_handlers.pop(job.name, None)
            if handler_id is not None:
                logger.remove(handler_id)


# -----------------------------------------------------------------------
# API
# -----------------------------------------------------------------------

@app.route("/rescan")
def api_rescan():
    scan_directories()
    return jsonify(status="ok")


@app.route("/trigger/<taskname>")
def api_trigger(taskname):
    taskid = get_task_id(taskname)
    job = scheduler.get_job(taskid)
    if not job:
        return jsonify(status="not found"), 404
    scheduler.modify_job(taskid, "default", next_run_time=datetime.utcnow())
    return jsonify(status="ok")


if __name__ == "__main__":
    logger.info("Tasse - Task as a service with a scheduler")

    for job in scheduler.get_jobs():
        logger.debug(f"- {job}")

    scheduler.add_job(
        scan_directories, "interval", seconds=60,
        id="scan_directories", replace_existing=True
    )

    scan_directories()

    for job in scheduler.get_jobs():
        logger.debug(f"- {job}")

    scheduler.start()
    app.run(host="0.0.0.0")