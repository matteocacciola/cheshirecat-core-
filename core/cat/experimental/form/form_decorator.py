from .cat_form import CatForm


# form decorator
def form(form: CatForm) -> CatForm:
    form._autopilot = True
    if form.name is None:
        form.name = form.__name__

    if form.triggers_map is None:
        form.triggers_map = {
            "start_example": form.start_examples,
            "description": [f"{form.name}: {form.description}"],
        }

    return form
