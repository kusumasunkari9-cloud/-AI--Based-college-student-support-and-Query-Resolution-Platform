(() => {
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const chatForm = document.getElementById('chat-form');
  const chatInput = document.getElementById('chat-input');
  const messages = document.getElementById('chat-messages');
  const compareForm = document.getElementById('compare-form');
  const compareResult = document.getElementById('compare-result');

  function toast(message, isError = false) {
    const region = document.getElementById('toast-region');
    if (!region) return;
    const item = document.createElement('div');
    item.className = `toast${isError ? ' error' : ''}`;
    item.textContent = message;
    region.append(item);
    window.setTimeout(() => item.remove(), 3800);
  }

  function addMessage(text, author, data = null) {
    const row = document.createElement('div');
    row.className = `message-row ${author === 'student' ? 'student-row' : 'assistant-row'}`;
    if (author !== 'student') {
      const avatar = document.createElement('div');
      avatar.className = 'assistant-avatar tiny';
      avatar.textContent = '✳';
      row.append(avatar);
    }
    const content = document.createElement('div');
    content.className = 'message-content';
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.textContent = text;
    content.append(bubble);
    if (author !== 'student') {
      const time = document.createElement('small');
      time.className = 'message-time';
      time.textContent = `Campus assistant${data?.domain ? ` · ${data.domain}` : ''}`;
      content.append(time);
      if (data?.citations?.length) {
        const citationBox = document.createElement('div');
        citationBox.className = 'citation-box';
        const title = document.createElement('b');
        title.textContent = 'Sources used';
        citationBox.append(title);
        const list = document.createElement('ul');
        data.citations.forEach((citation) => {
          const item = document.createElement('li');
          item.textContent = citation;
          list.append(item);
        });
        citationBox.append(list);
        content.append(citationBox);
      }
      if (data?.context_used?.length) {
        const context = document.createElement('small');
        context.className = 'context-note';
        context.textContent = `Profile context used: ${data.context_used.join(' · ')}`;
        content.append(context);
      }
      if (data?.query_log_id) {
        const feedback = document.createElement('div');
        feedback.className = 'feedback-row';
        const label = document.createElement('span');
        label.textContent = 'Was this helpful?';
        feedback.append(label);
        [[1, 'Yes, helpful'], [-1, 'Not quite']].forEach(([rating, labelText]) => {
          const button = document.createElement('button');
          button.type = 'button';
          button.textContent = labelText;
          button.addEventListener('click', async () => {
            try {
              const response = await fetch('/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
                body: JSON.stringify({ query_log_id: data.query_log_id, rating }),
              });
              if (!response.ok) throw new Error('Feedback could not be saved.');
              feedback.innerHTML = '';
              feedback.textContent = 'Thanks for your feedback.';
            } catch (error) {
              toast(error.message, true);
            }
          });
          feedback.append(button);
        });
        content.append(feedback);
      }
    }
    row.append(content);
    messages.append(row);
    messages.scrollTop = messages.scrollHeight;
  }

  async function ask(query) {
    if (!query || !messages) return;
    addMessage(query, 'student');
    const loading = document.createElement('div');
    loading.className = 'typing-indicator';
    loading.textContent = 'Checking available sources…';
    messages.append(loading);
    messages.scrollTop = messages.scrollHeight;
    try {
      const response = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({
          query,
          explain: document.getElementById('explain-mode')?.checked || false,
        }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Your question could not be sent.');
      loading.remove();
      addMessage(result.answer, 'assistant', result);
      if (result.ticket_id) toast(`Support ticket #${result.ticket_id} created.`);
    } catch (error) {
      loading.remove();
      addMessage(error.message || 'Something went wrong. Please try again.', 'assistant');
    }
  }

  if (chatForm) {
    chatForm.addEventListener('submit', (event) => {
      event.preventDefault();
      const question = chatInput.value.trim();
      if (!question) return;
      chatInput.value = '';
      chatInput.style.height = 'auto';
      ask(question);
    });
    chatInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        chatForm.requestSubmit();
      }
    });
    chatInput.addEventListener('input', () => {
      chatInput.style.height = 'auto';
      chatInput.style.height = `${Math.min(chatInput.scrollHeight, 140)}px`;
    });
    document.querySelectorAll('[data-prompt]').forEach((button) => {
      button.addEventListener('click', () => {
        chatInput.value = button.dataset.prompt;
        chatInput.focus();
      });
    });
    document.querySelector('.clear-chat')?.addEventListener('click', () => {
      messages.innerHTML = '';
      addMessage('Conversation cleared. Ask me anything about your college.', 'assistant');
    });
  }

  document.querySelector('[data-open-profile]')?.addEventListener('click', () => {
    const profile = document.getElementById('profile-form');
    profile.open = true;
    profile.scrollIntoView({ behavior: 'smooth', block: 'center' });
  });

  function addText(parent, tag, text, className = '') {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = text;
    parent.append(element);
    return element;
  }

  if (compareForm) {
    compareForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      compareResult.replaceChildren();
      addText(compareResult, 'p', 'Comparing document versions…', 'muted');
      try {
        const response = await fetch('/compare', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
          body: JSON.stringify(Object.fromEntries(new FormData(compareForm))),
        });
        const result = await response.json();
        compareResult.replaceChildren();
        if (!response.ok) throw new Error(result.error || 'Unable to compare these documents.');
        const status = addText(compareResult, 'div', result.affected ? 'This change may apply to you' : 'This change may not apply to you', `affected-banner ${result.affected ? 'affected' : 'not-affected'}`);
        status.setAttribute('role', 'status');
        addText(compareResult, 'p', result.reason, 'compare-reason');
        addText(compareResult, 'p', `Effective: ${result.effective_date} · Categories: ${result.categories.join(', ')}`, 'compare-meta');
        const list = document.createElement('div');
        list.className = 'diff-list';
        result.changes.forEach((change) => {
          const item = document.createElement('article');
          item.className = 'diff-item';
          if (change.old) addText(item, 'p', `− ${change.old}`, 'diff-old');
          if (change.new) addText(item, 'p', `+ ${change.new}`, 'diff-new');
          if (change.citations?.length) addText(item, 'small', `Sources: ${change.citations.join(' · ')}`, 'diff-citation');
          list.append(item);
        });
        compareResult.append(list);
        if (result.citations?.length) addText(compareResult, 'small', `Documents: ${result.citations.join(' · ')}`, 'diff-citation');
      } catch (error) {
        compareResult.replaceChildren();
        addText(compareResult, 'p', error.message, 'flash error');
      }
    });
  }

  document.querySelectorAll('.file-picker input, .upload-drop input').forEach((input) => {
    input.addEventListener('change', () => {
      const label = input.closest('label');
      const fileName = input.files?.[0]?.name;
      if (fileName && label) label.dataset.selectedFile = fileName;
    });
  });
})();
