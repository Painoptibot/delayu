def package_is_ready(project) -> bool:
    """Real rules in Task 4. Default True if no package model exists yet."""
    from delayu import models_invest as m

    InvestPackage = getattr(m, "InvestPackage", None)
    if InvestPackage is None:
        return True
    pkg = InvestPackage.objects.filter(project=project, is_active=True).first()
    if not pkg:
        return True
    return not pkg.items.filter(required=True, status="missing").exists()
