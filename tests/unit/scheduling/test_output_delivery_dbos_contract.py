"""DBOS-visible names of the output-delivery workers must not change.

DBOS persists queue names, workflow ids and function qualified names; renaming
or moving any of them breaks recovery of in-flight workflows. These tests pin
them (they must survive the move of ``backend/output/``).
"""

import contextlib
import inspect

import pytest
from scheduling import output_delivery

DBOS_FUNCTIONS = ["process_output_delivery_step", "output_delivery_workflow", "output_delivery_reconciler"]


def test_queue_and_schedule_names_are_stable():
    assert output_delivery.OUTPUT_QUEUE == "output-deliveries"
    assert output_delivery.OUTPUT_RECONCILER_QUEUE == "output-delivery-reconciler"
    assert output_delivery.OUTPUT_RECONCILER_SCHEDULE == "output-delivery-reconciler"


@pytest.mark.parametrize("name", DBOS_FUNCTIONS)
def test_dbos_function_identity_is_stable(name):
    function = getattr(output_delivery, name)
    for candidate in (function, inspect.unwrap(function)):
        assert candidate.__name__ == name
        assert candidate.__qualname__ == name
        assert candidate.__module__ == "scheduling.output_delivery"
    assert inspect.iscoroutinefunction(inspect.unwrap(function))


@pytest.mark.parametrize("name, params", [
    ("process_output_delivery_step", ["delivery_id", "generation"]),
    ("output_delivery_workflow", ["delivery_id", "generation"]),
    ("output_delivery_reconciler", ["scheduled_time", "context"]),
])
def test_dbos_function_signatures_are_stable(name, params):
    assert list(inspect.signature(inspect.unwrap(getattr(output_delivery, name))).parameters) == params


class FakeDbos:
    def __init__(self):
        self.enqueued = []

    def enqueue_workflow(self, queue, workflow, *args):
        self.enqueued.append((queue, workflow, args))


def test_enqueue_delivery_workflow_id_format(monkeypatch):
    workflow_ids = []
    fake = FakeDbos()

    @contextlib.contextmanager
    def set_workflow_id(workflow_id):
        workflow_ids.append(workflow_id)
        yield

    monkeypatch.setattr(output_delivery, "DBOS", fake)
    monkeypatch.setattr(output_delivery, "SetWorkflowID", set_workflow_id)

    assert output_delivery.enqueue_delivery(1, 2) == "output-delivery-1-g2"
    assert workflow_ids == ["output-delivery-1-g2"]
    assert fake.enqueued == [(output_delivery.OUTPUT_QUEUE, output_delivery.output_delivery_workflow, (1, 2))]
