"""T0.1 schema RED gate -- Category schema, RouteValue enum, BelongsTo edge,
NodeType.CATEGORY, and registry completeness.

All tests here must FAIL until writ/graph/schema.py gains:
  - RouteValue enum with exactly 7 values
  - VALID_ROUTES frozenset
  - Category model (category_id, name, routes, parent, description)
  - BelongsTo edge
  - NodeType.CATEGORY = 'Category'
  - 'Category' removed from RETRIEVABLE_NODE_TYPES
  - NODE_ID_FIELDS['Category'] = 'category_id'
  - NODE_ID_FIELDS['Abstraction'] = 'abstraction_id'
  - NODE_TYPE_MODELS['Category'] = Category
  - NODE_TYPE_MODELS['Abstraction'] = Abstraction
  - invariant set(NODE_ID_FIELDS) == set(NODE_TYPE_MODELS)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestRouteValueEnum:
    """RouteValue enum must carry exactly the 7 canonical route strings."""

    def test_all_seven_values_present(self) -> None:
        from writ.graph.schema import RouteValue

        expected = {"semantic", "scoped", "state", "action", "always_on", "pull", "ride_along"}
        actual = {rv.value for rv in RouteValue}
        assert actual == expected

    def test_valid_routes_frozenset_matches_enum(self) -> None:
        from writ.graph.schema import RouteValue, VALID_ROUTES

        enum_values = {rv.value for rv in RouteValue}
        assert VALID_ROUTES == enum_values
        assert isinstance(VALID_ROUTES, frozenset)


class TestCategoryModel:
    """Category model validation -- prefix, routes, dedup, defaults."""

    def test_instantiates_minimal(self) -> None:
        from writ.graph.schema import Category

        cat = Category(category_id="CAT-CODING-001", name="coding-rules", routes=["semantic"])
        assert cat.category_id == "CAT-CODING-001"
        assert cat.name == "coding-rules"
        assert cat.parent is None
        assert cat.description == ""

    def test_multiple_routes_accepted_and_deduped(self) -> None:
        from writ.graph.schema import Category

        cat = Category(
            category_id="CAT-PROC-001",
            name="process",
            routes=["semantic", "action", "semantic"],
        )
        # Duplicates must be collapsed; order is unspecified so compare as set.
        assert set(cat.routes) == {"semantic", "action"}

    def test_rejects_wrong_prefix(self) -> None:
        from writ.graph.schema import Category

        with pytest.raises(ValidationError):
            Category(category_id="SKL-PROC-001", name="bad-prefix", routes=["semantic"])

    def test_rejects_empty_routes(self) -> None:
        from writ.graph.schema import Category

        with pytest.raises(ValidationError):
            Category(category_id="CAT-CODING-001", name="coding-rules", routes=[])

    def test_rejects_invalid_route_value(self) -> None:
        from writ.graph.schema import Category

        with pytest.raises(ValidationError):
            Category(
                category_id="CAT-CODING-001",
                name="coding-rules",
                routes=["invalid-route"],
            )

    def test_parent_optional_string(self) -> None:
        from writ.graph.schema import Category

        cat = Category(
            category_id="CAT-FW-MAGENTO2-001",
            name="frameworks/magento2",
            routes=["semantic", "scoped"],
            parent="CAT-CODING-001",
        )
        assert cat.parent == "CAT-CODING-001"

    def test_description_optional_string(self) -> None:
        from writ.graph.schema import Category

        cat = Category(
            category_id="CAT-PROC-001",
            name="process",
            routes=["state", "action", "pull"],
            description="Workflow and orchestration nodes.",
        )
        assert cat.description == "Workflow and orchestration nodes."

    def test_discipline_counters_uses_ride_along(self) -> None:
        from writ.graph.schema import Category

        cat = Category(
            category_id="CAT-DISCIPLINE-COUNTERS-001",
            name="discipline-counters",
            routes=["ride_along"],
        )
        assert "ride_along" in cat.routes


class TestBelongsToEdge:
    """BelongsTo edge model -- source_id, target_id, edge-type string."""

    def test_instantiates(self) -> None:
        from writ.graph.schema import BelongsTo

        edge = BelongsTo(source_id="SKL-PROC-BRAIN-001", target_id="CAT-PROC-001")
        assert edge.source_id == "SKL-PROC-BRAIN-001"
        assert edge.target_id == "CAT-PROC-001"

    def test_edge_type_string(self) -> None:
        from writ.graph.schema import BelongsTo

        edge = BelongsTo(source_id="SKL-PROC-BRAIN-001", target_id="CAT-PROC-001")
        # The edge-type string must be 'BELONGS_TO' (Neo4j relationship label).
        assert edge.edge_type == "BELONGS_TO"

    def test_rejects_empty_source(self) -> None:
        from writ.graph.schema import BelongsTo

        with pytest.raises(ValidationError):
            BelongsTo(source_id="", target_id="CAT-PROC-001")

    def test_rejects_empty_target(self) -> None:
        from writ.graph.schema import BelongsTo

        with pytest.raises(ValidationError):
            BelongsTo(source_id="SKL-PROC-BRAIN-001", target_id="")


class TestNodeTypeEnum:
    """NodeType enum gains CATEGORY; Category is NOT retrievable."""

    def test_category_member_exists(self) -> None:
        from writ.graph.schema import NodeType

        assert NodeType.CATEGORY == "Category"

    def test_category_not_in_retrievable_node_types(self) -> None:
        from writ.graph.schema import NodeType, RETRIEVABLE_NODE_TYPES

        assert NodeType.CATEGORY not in RETRIEVABLE_NODE_TYPES


class TestRegistryCompleteness:
    """NODE_ID_FIELDS and NODE_TYPE_MODELS must be in sync and include Category + Abstraction."""

    def test_category_in_node_id_fields(self) -> None:
        from writ.graph.schema import NODE_ID_FIELDS

        assert "Category" in NODE_ID_FIELDS
        assert NODE_ID_FIELDS["Category"] == "category_id"

    def test_abstraction_in_node_id_fields(self) -> None:
        from writ.graph.schema import NODE_ID_FIELDS

        assert "Abstraction" in NODE_ID_FIELDS
        assert NODE_ID_FIELDS["Abstraction"] == "abstraction_id"

    def test_category_in_node_type_models(self) -> None:
        from writ.graph.schema import NODE_TYPE_MODELS, Category

        assert "Category" in NODE_TYPE_MODELS
        assert NODE_TYPE_MODELS["Category"] is Category

    def test_abstraction_in_node_type_models(self) -> None:
        from writ.graph.schema import NODE_TYPE_MODELS, Abstraction

        assert "Abstraction" in NODE_TYPE_MODELS
        assert NODE_TYPE_MODELS["Abstraction"] is Abstraction

    def test_all_node_types_have_id_field_and_model(self) -> None:
        from writ.graph.schema import NODE_ID_FIELDS, NODE_TYPE_MODELS

        assert set(NODE_ID_FIELDS) == set(NODE_TYPE_MODELS), (
            "NODE_ID_FIELDS and NODE_TYPE_MODELS are out of sync -- "
            f"id_fields-only: {set(NODE_ID_FIELDS)-set(NODE_TYPE_MODELS)}, "
            f"models-only: {set(NODE_TYPE_MODELS)-set(NODE_ID_FIELDS)}"
        )
