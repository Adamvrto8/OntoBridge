from ontobridge.agents.governance.rules.base import Rule
from ontobridge.agents.governance.rules.matching import (
    Rule01ExactPrefLabelMatch,
    Rule02AcronymExpansionMatch,
    Rule03FuzzyLabelMatch,
)
from ontobridge.agents.governance.rules.naming import (
    Rule04UserRejectedSynonym,
    Rule05CrossDomainCompatibleMatch,
    Rule06UppercaseShortNoContext,
    Rule07SingleNounNoQualifier,
)
from ontobridge.agents.governance.rules.quality import (
    Rule08DefinitionTooShort,
    Rule09CircularDefinition,
    Rule10NoPolicySource,
    Rule11MultiPolicySource,
)
from ontobridge.agents.governance.rules.conflict import (
    Rule12FIBOMatchDivergent,
    Rule13DeprecatedTermMatch,
    Rule14CrossDomainIncompatibleMatch,
)


def default_rules() -> list[Rule]:
    return [
        Rule01ExactPrefLabelMatch(),
        Rule02AcronymExpansionMatch(),
        Rule03FuzzyLabelMatch(),
        Rule04UserRejectedSynonym(),
        Rule05CrossDomainCompatibleMatch(),
        Rule06UppercaseShortNoContext(),
        Rule07SingleNounNoQualifier(),
        Rule08DefinitionTooShort(),
        Rule09CircularDefinition(),
        Rule10NoPolicySource(),
        Rule11MultiPolicySource(),
        Rule12FIBOMatchDivergent(),
        Rule13DeprecatedTermMatch(),
        Rule14CrossDomainIncompatibleMatch(),
    ]


__all__ = ["Rule", "default_rules"]
