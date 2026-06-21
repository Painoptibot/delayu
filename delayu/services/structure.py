"""M04 — организационная структура и штатное расписание."""
from collections import defaultdict

from delayu.models_business import Department, Position, UserAssignment


def department_tree(organization):
    """Плоский список узлов с уровнем вложенности для отрисовки дерева."""
    depts = list(
        Department.objects.filter(organization=organization)
        .select_related("parent", "manager")
        .prefetch_related("positions")
    )
    by_parent = defaultdict(list)
    for d in depts:
        by_parent[d.parent_id].append(d)

    def walk(parent_id=None, level=0):
        nodes = []
        for d in sorted(by_parent[parent_id], key=lambda x: (getattr(x, "sort_order", 0), x.name)):
            pos_count = d.positions.count()
            assign_count = UserAssignment.objects.filter(department=d).count()
            nodes.append(
                {
                    "department": d,
                    "level": level,
                    "positions_count": pos_count,
                    "assignments_count": assign_count,
                    "children": walk(d.id, level + 1),
                }
            )
        return nodes

    return walk(None)


def flatten_tree(nodes):
    rows = []
    for node in nodes:
        rows.append(node)
        rows.extend(flatten_tree(node["children"]))
    return rows


def department_card_context(department):
    positions = department.positions.all().order_by("name")
    assignments = (
        UserAssignment.objects.filter(department=department)
        .select_related("user", "position")
        .order_by("user__last_name")
    )
    return {
        "department": department,
        "positions": positions,
        "assignments": assignments,
        "parent_name": department.parent.name if department.parent else "—",
        "manager_name": department.manager.get_full_name() or department.manager.username
        if department.manager
        else "—",
    }


def position_card_context(position):
    return {
        "position": position,
        "department": position.department,
        "assignments_count": UserAssignment.objects.filter(position=position).count(),
    }
