CSS = """
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-T3c6CoIi6uLrA9TneNEoa7RxnatzjcDSCmG1MXxSR1GAsXEV/Dwwykc2MPK8M2HN" crossorigin="anonymous">
<link rel="stylesheet" href="https://unpkg.com/tippy.js@6/animations/scale.css" />
<link href="https://getbootstrap.com/docs/5.3/assets/css/docs.css" rel="stylesheet">
"""
JS = """
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js" integrity="sha384-C6RzsynM9kWDrMNeT87bh95OGNyZPhcTNXj1NW7RuBCsyN/o0jlpcV8Qyq46cDfL" crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/@popperjs/core@2.11.8/dist/umd/popper.min.js" integrity="sha384-I7E8VVD/ismYTF4hNIPjVp/Zjvgyol6VFvRkX/vR+Vc4jQkC+hVqc2pM8ODewa9r" crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.min.js" integrity="sha384-BBtl+eGJRgqQAUMxJ7pMwbEyER4l1g+O15P+16Ep7Q9Q+zqX6gSbd85u4mG4QzX+" crossorigin="anonymous"></script>
<script src="https://unpkg.com/@popperjs/core@2"></script>
<script src="https://unpkg.com/tippy.js@6"></script>
"""

STYLE = """
<style>

.btn {
    border: none;
    margin-top: 10px;
    margin-bottom: 10px;
}

.btn-none {
    background-color: green;
}

.btn-misp {
    background-color: yellow;
}

.btn-omis {
    background-color: #6c757d;
}

.btn-inse {
    background-color: #c02a2a;
}

.btn-inte {
    background-color: #ecc0eedc;
}

.btn-paus {
    background-color: #f8f9fa;
}

.btn-dull {
    background-color: blueviolet;
}

.tippy-box[data-theme~='tomato'] {
    background-color: blueviolet;
    color: white;
}

.custom-tooltip {
    --bs-tooltip-bg: var(--bd-violet-bg);
    --bs-tooltip-color: var(--bs-white);
}

</style>
"""

SCRIPT = """
<script>
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]')
    const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl))
    // With the above scripts loaded, you can call `tippy()` with a CSS
    // selector and a `content` prop:
    tippy('[data-tippy-content]', {
        allowHTML: true,
        theme: 'tomato',
    });
</script>
"""
