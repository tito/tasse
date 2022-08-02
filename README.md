# Tasse - Task as a service with a scheduler

Tasse is a task executor:
- discover tasks to run from a tasks directory
- each task have their own scheduler rules
- can trigger a task from an API
- a task can have a poetry environment for the execution

This is intented to be deployed in Docker with a shared directory where you put your scripts in.

There is limitation:
- no arguments can be passed to tasks
- every tasks must have a scheduler

## How to run

```
$ poetry install
$ poetry run server.py
```

## Example

Let's create an hello world task.
1. Create a directory in `data/tasks/helloworld`
2. Create your task in `data/tasks/helloworld/task.py` with

```python
print("Hello world")
```

3. Create a `data/tasks/helloworld/task.yaml` with

```yaml
scheduler:
  trigger: interval
  seconds: 10
```

4. Wait a minute, then you should have the execution logs in
   `data/logs/helloworld/log.txt`


## Trigger format

The trigger format follow the options of APScheduler project

### Interval trigger

```yaml
scheduler:
  trigger: interval
  # weeks (int) – number of weeks to wait
  # days (int) – number of days to wait
  # hours (int) – number of hours to wait
  # minutes (int) – number of minutes to wait
  # seconds (int) – number of seconds to wait
  # start_date (str) – starting point for the interval calculation
  # end_date (str) – latest possible date/time to trigger on
  # timezone (str) – time zone to use for the date/time calculations
  # jitter (int) – delay the job execution by jitter seconds at most
```

Examples:

Every 10 seconds
```yaml
scheduler:
  trigger: interval
  seconds: 10
```

Every days
```yaml
scheduler:
   trigger: interval
   days: 1
```

### Cron trigger

```yaml
scheduler:
  trigger: cron
  # year (int|str) – 4-digit year
  # month (int|str) – month (1-12)
  # day (int|str) – day of month (1-31)
  # week (int|str) – ISO week (1-53)
  # day_of_week (int|str) – number or name of weekday (0-6 or mon,tue,wed,thu,fri,sat,sun)
  # hour (int|str) – hour (0-23)
  # minute (int|str) – minute (0-59)
  # second (int|str) – second (0-59)
  # start_date (str) – earliest possible date/time to trigger on (inclusive)
  # end_date (str) – latest possible date/time to trigger on (inclusive)
  # timezone (str) – time zone to use for the date/time calculations (defaults to scheduler timezone)
  # jitter (int) – delay the job execution by jitter seconds at most
```

Examples:

Every monday and thuesday at 5pm
```yaml
scheduler:
  trigger: cron
  day_of_week: mon,tue
  hour: 5
```

## Directories

- `data/tasks` - List of the tasks that can be run
- `data/logs` - Execution logs of your tasks
- `data/venv` - If necessary, venv for your tasks

## Acknowledgments

Thanks to [Cozy Air](https://cozyair.fr) for their support over this opensource software !