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

/** SMS feedback is progressive enhancement: the server enforces every limit. */
(() => {
  const sendForm = document.querySelector('[data-sms-send]');
  if (!sendForm) return;
  const button = sendForm.querySelector('button');
  const status = sendForm.querySelector('[data-send-status]');
  const readyAt = Date.now() + Number(button.dataset.cooldown || 0) * 1000;
  let submitting = false;
  function update() {
    if (submitting) return;
    const remaining = Math.max(0, Math.ceil((readyAt - Date.now()) / 1000));
    button.disabled = remaining > 0;
    button.textContent = remaining ? `Request again in ${remaining}s` : button.dataset.idleLabel;
  }
  update();
  const timer = setInterval(update, 1000);
  sendForm.addEventListener('submit', () => {
    submitting = true;
    clearInterval(timer);
    button.disabled = true;
    button.textContent = 'Sending request…';
    sendForm.setAttribute('aria-busy', 'true');
    status.textContent = 'Contacting the delivery provider. Please keep this page open.';
  });
  const verify = document.querySelector('[data-sms-verify]');
  verify?.addEventListener('submit', () => {
    const submit = verify.querySelector('button');
    submit.disabled = true;
    submit.textContent = 'Checking code…';
    verify.setAttribute('aria-busy', 'true');
  });
  // Restore usable buttons when the browser returns a page from its back cache.
  window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });
})();
