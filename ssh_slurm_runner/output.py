from typing import Union
from rich.table import Table
from ssh_slurm_runner.slurmrunner import SlurmJob


def make_table(job_or_title: Union[SlurmJob, str] = None) -> Table:
    title = job_or_title or ""
    if type(job_or_title) == SlurmJob:
        title = f"Job {job_or_title.id}"

    table = Table(title=title, style="bold")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("State")

    if job_or_title is None or type(job_or_title) != SlurmJob:
        return table

    for task in job_or_title.tasks:
        table.add_row(str(task.id), task.name, task.state)

    return table
