"""Every component's render call takes help=, also those that override __call__."""

import inspect

import pytest

from openms_insight.components.lineplot import LinePlot
from openms_insight.components.mirrorplot import MirrorPlot
from openms_insight.components.pca import PCAPlot
from openms_insight.components.sequenceview import SequenceView
from openms_insight.components.volcanoplot import VolcanoPlot


@pytest.mark.parametrize("cls", [LinePlot, MirrorPlot, PCAPlot, SequenceView, VolcanoPlot])
def test_call_accepts_help(cls):
    assert "help" in inspect.signature(cls.__call__).parameters
