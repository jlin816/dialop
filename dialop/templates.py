from jinja2 import Template
from jinja2 import Environment, PackageLoader, select_autoescape
env = Environment(
    trim_blocks=True,
    lstrip_blocks=True,
)

OptimizationPromptTemplateStr = (
"""Reviewer Paper Similarity Scores:
{{ table }}

{% for m in messages %}
{% if m.type == "message" %}
{{ "You:" if m.player == player_id else "Partner:" }} [message] {{ m.message.data.strip() }}
{% elif m.type == "proposal" and any(m.proposal) %}
{{ "You:" if m.player == player_id else "Partner:" }} [propose] {{ m.proposal }}
{% elif m.type == "proposal_response" %}
{{ "You:" if m.player == player_id else "Partner:" }} {{ "[accept]" if m.response.accept else "[reject]" }}
{% endif %}
{% endfor %}"""
)
OptimizationPromptTemplate = env.from_string(OptimizationPromptTemplateStr)

MediationUserPromptTemplateStr = (
"""Flights:
id | carrier | price | times
{% for f in flights %}
{{ loop.index0 }} | {{ pp_flight(f) }}
{% endfor %}
Private calendar:
id | importance | times
{% for e in unshared_calendar %}
{{ loop.index0 }} | {{ pp_event(e, show_importance=True) }}
{% endfor %}
Shared calendar (visible to assistant):
id | importance | times
{% for e in shared_calendar %}
{{ loop.index0 }} | {{ pp_event(e, show_importance=True) }}
{% endfor %}

{% for m in messages %}
{% if m.vroom == player_id or m.type == "proposal" %}
{% if m.type == "message" %}
{{ "You:" if m.player == player_id else "Agent:" }} [message] {{ m.message.data }}
{% elif m.type == "proposal" %}
Agent: [propose] {{ format_proposal(m.proposals[player_id], player_id) }}
{% elif m.type == "proposal_response" %}
You: {{ "[accept]" if m.response.accept else "[reject]" }}
{% else %}
UNKNOWN TYPE!!!!!
{% endif %}
{% endif %}
{% endfor %}"""
)
MediationUserPromptTemplate = env.from_string(MediationUserPromptTemplateStr)

MediationProposalTemplateStr = (
"""{{ flight_id }} | {{ pp_flight(flight) }}
Conflicting meetings:
{% for e in proposal.conflicts %}
importance | times
{{ pp_event(e, show_importance=True) }}
{% endfor %}
Score:
- ({{ proposal.cost.calendar }}) Try not to skip important meetings
- ({{ proposal.cost.price }}) Get a good deal on the flight price
- ({{ proposal.cost.arrival_time }}) Have everyone arrive around the same time
Total score: {{ proposal.cost.total }}
"""
)
MediationProposalTemplate = env.from_string(MediationProposalTemplateStr)

MediationAgentPromptTemplateStr = (
"""
{% for pdata in player_data %}
User {{ loop.index0 }} Information
Flights:
id | carrier | price | times
{% for f in pdata.flights %}
{{ loop.index0 }} | {{ pp_flight(f) }}
{% endfor %}
Calendar:
id | times
{% for e in pdata.shared_calendar %}
{{ loop.index0 }} | {{ pp_event(e, show_importance=False) }}
{% endfor %}
{% endfor %}

{% for m in messages %}
{% if m.type == "message" %}
{{ "User " + m.player|string if m.player != 2 else "You to " + m.vroom|string }}: [message] {{ m.message.data }}
{% elif m.type == "proposal" %}
You to all: [propose] user 0: id {{ m.proposals[0].flight_id }}, user 1: id {{ m.proposals[1].flight_id }}
Flight for user 0: {{ m.proposals[0].flight_id }} | {{ pp_flight(m.proposals[0].proposal_data) }}
Flight for user 1: {{ m.proposals[1].flight_id }} | {{ pp_flight(m.proposals[1].proposal_data) }}
{% elif m.type == "proposal_response" %}
{{ "User " + m.player|string }}: {{ "[accept]" if m.response.accept else "[reject]" }}
{% endif %}
{% endfor %}""")
MediationAgentPromptTemplate = env.from_string(MediationAgentPromptTemplateStr)


### Planning 
PlanningUserPromptTemplateStr = (
"""Travel Preferences:
{{ travel_doc }}

{% for m in messages %}
{% if m.type == "message" %}
{{ "You:" if m.player == player_id else "Agent:" }} [message] {{ m.message.data.strip() }}
{% elif m.type == "proposal" and any(m.proposal) %}
Agent: [propose] {{ format_proposal(m.proposal, m.scores.itinerary_scores, m.scores.scores_by_event, m.scores.total) }}
{% elif m.type == "proposal_response" %}
You: {{ "[accept]" if m.response.accept else "[reject]" }}
{% else %}
UNKNOWN TYPE!!!!!
{% endif %}
{% endfor %}"""
)
PlanningUserPromptTemplate = env.from_string(PlanningUserPromptTemplateStr)

PlanningProposalTemplateStr = (
"""{{ proposal_msg }}
Proposal Score:
{% for evt in proposal %}
{% if evt is not none %}
{{ loop.index }}) (score: {{ evt_scores[loop.index0] }}) {{ evt.name }}
{% if evt.type == "event" %}
{% for feat, val in evt.features.items() %}
{{ feat }}: {{ val }}
{% endfor %}
{% endif %}
{% else %}
{{ loop.index }}) Empty
{% endif %}
{% endfor %}

Overall Checklist:
{% for it_score in itinerary_scores %}
{{ "YES" if it_score.score >= 0 else "NO" }} (score: {{ it_score.score }}) {{
it_score.desc }}
{% endfor %}
TOTAL SCORE: {{ score_calculation }}
"""
)
PlanningProposalTemplate = env.from_string(PlanningProposalTemplateStr)

QueryExecutorTemplateStr = (
"""Database:
{% for site in sites %}
{{ site }}
{% endfor %}

{% for ex in example_queries %}
Query: {{ ex.query }}
Result:
{{ ex.result }}

{% endfor %}
"""
)
QueryExecutorTemplate = env.from_string(QueryExecutorTemplateStr)


PlanningAgentPromptTemplateStr = (
"""
{% for m in messages %}
{% if m.type == "message" %}
{{ "User:" if m.player != player_id else "You:" }} [message] {{ m.message.data }}
{% elif m.type == "proposal" %}
You: [propose] {{ format_proposal(m.proposal) }}
{% elif m.type == "proposal_response" %}
User: {{ "[accept]" if m.response.accept else "[reject]" }}
{% endif %}
{% endfor %}""")
PlanningAgentPromptTemplate = env.from_string(PlanningAgentPromptTemplateStr)
