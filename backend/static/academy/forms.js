/**
 * Show the education fields relevant to the applicant's category.
 * This is a usability aid: ApplicationForm repeats required-field validation
 * on the server, so disabling JavaScript cannot bypass the application rules.
 */
(() => {
  // Other portal pages share this asset but do not contain the application form.
  const form = document.querySelector('[data-application-form]');
  if (!form) return;

  const kind = form.querySelector('[name=kind]');
  const groups = {
    student: ['faculty', 'department', 'level'],
    graduate: ['qualification', 'graduation_year'],
    education: ['institution', 'course'],
    adult: ['occupation'],
  };

  function update() {
    const category = kind.value;
    for (const [group, names] of Object.entries(groups)) {
      // Institution and course apply to both students and graduates.
      const show = group === 'education'
        ? ['student', 'graduate'].includes(category)
        : category === group;

      for (const name of names) {
        const row = form.querySelector('[data-field="' + name + '"]');
        if (!row) continue;
        row.hidden = !show;
        const input = row.querySelector('input,select,textarea');
        // Hidden category fields must not submit stale values or block the form.
        input.disabled = !show;
        input.required = show && group !== 'adult';
      }
    }
  }

  kind.addEventListener('change', update);
  update(); // Restore the correct fields after validation errors or page reloads.
})();
