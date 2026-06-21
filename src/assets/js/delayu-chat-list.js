'use strict';

/** Чат ДелаЮ: реальная отправка сообщений (без demo-хендлера app-chat.js). */
document.addEventListener('DOMContentLoaded', function () {
  var form = document.querySelector('.delayu-chat-send-form');
  if (!form) return;

  form.addEventListener('submit', function (e) {
    var input = form.querySelector('input[name="body"]');
    if (!input || !input.value.trim()) {
      e.preventDefault();
    }
  });

  var history = document.getElementById('delayuChatMessages');
  if (history) {
    var body = document.querySelector('.chat-history-body');
    if (body) body.scrollTop = body.scrollHeight;
  }
});
