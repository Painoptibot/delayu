"""Собрать chat/list.html из Materialize app_chat_src + Django."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "delayu" / "templates" / "platform" / "chat"
src = (ROOT / "app_chat_src.html").read_text(encoding="utf-8")

REPL = [
    ("{% load i18n %}\n", ""),
    ("{% url 'index' %}", "{% url 'platform-home' %}"),
    ("Chat - Apps", "Внутренний чат — ДелаЮ"),
    ("John Doe", "{{ request.user.get_full_name|default:request.user.username }}"),
    ("UI/UX Designer", "{{ active_role|default:'Сотрудник' }}"),
    ("About", "О себе"),
    ("Status", "Статус"),
    ("Online", "В сети"),
    ("Away", "Отошёл"),
    ("Do not Disturb", "Не беспокоить"),
    ("Offline", "Не в сети"),
    ("Settings", "Настройки"),
    ("Logout", "Выход"),
    ("Search...", "Поиск чатов…"),
    ("Chats", "Чаты"),
    ("No Chats Found", "Чаты не найдены"),
    ("Contacts", "Участники"),
    ("No Contacts Found", "Нет контактов"),
    ("Select a contact to start a conversation.", "Выберите чат в списке слева."),
    ("Select Contact", "Открыть чаты"),
    ("View Contact", "Профиль чата"),
    ("Mute Notifications", "Отключить уведомления"),
    ("Block Contact", "Заблокировать"),
    ("Clear Chat", "Очистить переписку"),
    ("Report", "Пожаловаться"),
    ("btn btn-text-secondary", "btn btn-text-heading"),
]

for old, new in REPL:
    src = src.replace(old, new)

# Replace demo chat list with Django loop
start = src.index('<ul class="list-unstyled chat-contact-list py-2 mb-0" id="chat-list">')
end = src.index("</ul>", start) + len("</ul>")
rooms_tpl = """<ul class="list-unstyled chat-contact-list py-2 mb-0" id="chat-list">
          <li class="chat-contact-list-item chat-contact-list-item-title mt-0">
            <h5 class="text-primary mb-0">Чаты</h5>
          </li>
          {% if can_create %}
          <li class="px-4 pb-2"><a href="{% url 'platform-chat-create' %}" class="btn btn-sm btn-primary w-100"><i class="ri-add-line"></i> Новый чат</a></li>
          {% endif %}
          {% for room in rooms %}
          <li class="chat-contact-list-item mb-1">
            <a href="{% url 'platform-chat' %}?room={{ room.pk }}" class="d-flex align-items-center delayu-chat-room-link{% if active_room and active_room.pk == room.pk %} active{% endif %}">
              <div class="flex-shrink-0 avatar">
                <span class="avatar-initial rounded-circle bg-label-secondary">{{ room.name|slice:":1"|upper }}</span>
              </div>
              <div class="chat-contact-info flex-grow-1 ms-4">
                <div class="d-flex justify-content-between align-items-center">
                  <h6 class="chat-contact-name text-truncate m-0 fw-normal">{{ room.name }}</h6>
                </div>
                <small class="chat-contact-status text-truncate">{% if room.case %}Дело {{ room.case.number }}{% else %}Общий чат{% endif %}</small>
              </div>
            </a>
          </li>
          {% empty %}
          <li class="chat-contact-list-item px-4 py-3 text-muted small">Нет чатов</li>
          {% endfor %}
        </ul>"""
src = src[:start] + rooms_tpl + src[end:]

# Hide contacts demo block
c_start = src.index('<ul class="list-unstyled chat-contact-list mb-0 py-2" id="contact-list">')
c_end = src.index("</ul>", c_start) + len("</ul>")
src = src[:c_start] + '<ul class="list-unstyled chat-contact-list mb-0 py-2 d-none" id="contact-list"></ul>' + src[c_end:]

# Conversation panel visibility
src = src.replace(
    'id="app-chat-conversation"',
    'id="app-chat-conversation"{% if active_room %} style="display:none!important"{% endif %}',
    1,
)
src = src.replace(
    'id="app-chat-history"',
    'id="app-chat-history"{% if not active_room %} class="col app-chat-history d-none"{% else %} class="col app-chat-history"{% endif %}',
    1,
)

# Replace header in history when active room
if "Felecia Rower" in src:
    src = src.replace(
        "<h6 class=\"m-0 fw-normal\">Felecia Rower</h6>",
        "{% if active_room %}<h6 class=\"m-0 fw-normal\">{{ active_room.name }}</h6>{% else %}<h6 class=\"m-0 fw-normal\">Чат</h6>{% endif %}",
        1,
    )
    src = src.replace(
        '<small class="user-status text-body">NextJS developer</small>',
        '{% if active_room.case %}<small class="user-status text-body">Дело {{ active_room.case.number }}</small>{% else %}<small class="user-status text-body">Внутренний чат</small>{% endif %}',
        1,
    )

# Replace messages body - find first chat-history ul
h_start = src.index('<ul class="list-unstyled chat-history">')
h_end = src.index("</ul>", h_start) + len("</ul>")
msgs = """<ul class="list-unstyled chat-history" id="delayuChatMessages">
            {% for msg in messages %}
            <li class="chat-message{% if msg.author_id == request.user.id %} chat-message-right{% endif %}">
              <div class="d-flex overflow-hidden">
                {% if msg.author_id != request.user.id %}
                <div class="user-avatar flex-shrink-0 me-4">
                  <div class="avatar avatar-sm"><span class="avatar-initial rounded-circle bg-label-secondary">{{ msg.author.username|slice:":1"|upper }}</span></div>
                </div>
                {% endif %}
                <div class="chat-message-wrapper flex-grow-1">
                  <div class="chat-message-text"><p class="mb-0">{{ msg.body|linebreaksbr }}</p></div>
                  <div class="{% if msg.author_id == request.user.id %}text-end{% endif %} text-body-secondary mt-1">
                    {% if msg.author_id == request.user.id %}<i class="icon-base ri ri-check-double-line icon-16px text-success me-1"></i>{% endif %}
                    <small>{{ msg.created_at|date:"d.m.Y H:i" }}</small>
                  </div>
                </div>
                {% if msg.author_id == request.user.id %}
                <div class="user-avatar flex-shrink-0 ms-4">
                  <div class="avatar avatar-sm"><img src="{{ avatar_url }}" alt="" class="rounded-circle" /></div>
                </div>
                {% endif %}
              </div>
            </li>
            {% empty %}
            <li class="text-center text-muted py-4">Нет сообщений</li>
            {% endfor %}
          </ul>"""
src = src[:h_start] + msgs + src[h_end:]

# Replace footer form - find chat-history-footer or form-send-message
if 'form-send-message' in src:
    pass
elif "chat-history-footer" in src:
    pass

# Inject send form before closing chat-history-wrapper - search chat-history-footer
footer_marker = '<div class="chat-history-footer'
if footer_marker in src:
    idx = src.index(footer_marker)
    # replace until next </form> block - simpler append after body
    pass

# Add comms nav after block content
src = src.replace(
    "{% block content %}\n<div class=\"app-chat",
    "{% block content %}\n{% include \"platform/comms/_nav.html\" %}\n<div class=\"app-chat",
    1,
)

if "delayu-chat-room-link" not in src:
    src = src.replace(
        "{% block page_css %}\n{{ block.super }}",
        "{% block page_css %}\n{{ block.super }}\n<style>.delayu-chat-room-link.active{background:rgba(var(--bs-primary-rgb),.12);border-radius:.375rem}.app-chat .btn-text-heading,.app-chat .btn-text-heading i{color:var(--bs-heading-color)!important}</style>",
        1,
    )

extra_js = """
{% block page_js %}{{ block.super }}
<script>
document.addEventListener('DOMContentLoaded', function () {
  var el = document.getElementById('delayuChatMessages');
  if (el) el.parentElement.scrollTop = el.parentElement.scrollHeight;
  document.querySelectorAll('.avatar-preset-radio').forEach(function (r) {
    r.addEventListener('change', function () {
      var img = document.getElementById('cabinetAvatarPreview');
      if (img && r.nextElementSibling) img.src = r.nextElementSibling.src;
    });
  });
});
</script>
{% endblock page_js %}
"""
# Fix footer - find placeholder message form
import re
src = re.sub(
    r'<form class="form-send-message[^"]*">.*?</form>',
    """{% if active_room %}<form class="form-send-message" method="post" action="{% url 'platform-chat-send' active_room.pk %}">
          {% csrf_token %}
          <div class="message-input d-flex align-items-center">
            <input type="text" name="body" class="form-control border-0 shadow-none" placeholder="Сообщение…" required maxlength="4000" />
            <button type="submit" class="btn btn-primary ms-2"><i class="icon-base ri ri-send-plane-fill"></i></button>
          </div>
        </form>{% endif %}""",
    src,
    count=1,
    flags=re.DOTALL,
)

if "{% block page_js %}" in src and "delayuChatMessages" not in src.split("page_js")[-1]:
    src = src.replace(
        '<script src="{% static \'js/app-chat.js\' %}"></script>',
        '<script src="{% static \'js/app-chat.js\' %}"></script>\n<script>document.addEventListener("DOMContentLoaded",function(){var el=document.getElementById("delayuChatMessages");if(el&&el.parentElement)el.parentElement.scrollTop=el.parentElement.scrollHeight;});</script>',
    )

(ROOT / "list.html").write_text(src, encoding="utf-8")
print("wrote", ROOT / "list.html")
