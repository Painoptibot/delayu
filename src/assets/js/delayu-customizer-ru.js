'use strict';

/** Русские подписи панели настройки темы (Materialize Template Customizer). */
if (typeof TemplateCustomizer !== 'undefined') {
  TemplateCustomizer.LANGUAGES.ru = {
    panel_header: 'Настройка интерфейса',
    panel_sub_header: 'Настройка и предпросмотр в реальном времени',
    theming_header: 'Оформление',
    color_label: 'Основной цвет',
    theme_label: 'Тема',
    skin_label: 'Оформление меню',
    semiDark_label: 'Полутёмное меню',
    layout_header: 'Макет',
    layout_label: 'Меню (навигация)',
    layout_header_label: 'Тип шапки',
    content_label: 'Контент',
    layout_navbar_label: 'Панель навигации',
    direction_label: 'Направление текста',
    module_hints_label: 'Подсказки модулей',
  };

  var optionTitles = {
    primary: 'Основной',
    success: 'Зелёный',
    warning: 'Жёлтый',
    danger: 'Красный',
    info: 'Синий',
    light: 'Светлая',
    dark: 'Тёмная',
    system: 'Системная',
    default: 'Обычное',
    bordered: 'С рамкой',
    expanded: 'Развёрнуто',
    collapsed: 'Свёрнуто',
    sticky: 'Закреплена',
    static: 'Статичная',
    hidden: 'Скрыта',
    fixed: 'Фиксированная',
    compact: 'Компактный',
    wide: 'Широкий',
    ltr: 'Слева направо',
    rtl: 'Справа налево',
  };

  function translateOptions(list) {
    if (!list) return;
    list.forEach(function (item) {
      if (item && optionTitles[item.name]) item.title = optionTitles[item.name];
    });
  }

  translateOptions(TemplateCustomizer.COLORS);
  translateOptions(TemplateCustomizer.THEMES);
  translateOptions(TemplateCustomizer.SKINS);
  translateOptions(TemplateCustomizer.LAYOUTS);
  translateOptions(TemplateCustomizer.NAVBAR_OPTIONS);
  translateOptions(TemplateCustomizer.HEADER_TYPES);
  translateOptions(TemplateCustomizer.CONTENT);
  translateOptions(TemplateCustomizer.DIRECTIONS);

  document.addEventListener('DOMContentLoaded', function () {
    window.setTimeout(function () {
      var reset = document.querySelector('.template-customizer-reset-btn');
      if (!reset) return;
      reset.setAttribute('title', 'Сбросить оформление');
      reset.setAttribute('aria-label', 'Сбросить оформление');
      reset.setAttribute('data-bs-original-title', 'Сбросить оформление');
    }, 0);
  });
}
