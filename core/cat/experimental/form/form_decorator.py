from .cat_form import CatForm


# form decorator
def form(this_form: CatForm) -> CatForm:
    this_form._autopilot = True
    if this_form.name is None:
        this_form.name = this_form.__name__

    if this_form.triggers_map is None:
        this_form.triggers_map = {
            "start_example": this_form.start_examples,
            "description": [f"{this_form.name}: {this_form.description}"],
        }

    return this_form
