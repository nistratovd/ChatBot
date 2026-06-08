#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

RUN_MODE="docker"
LOCAL_DATABASE_URL=""

print_header() {
  printf '\n=== Telegram Quiz Bot: меню консольных команд ===\n'
  printf 'Режим запуска: %s\n' "$RUN_MODE"
  if [[ "$RUN_MODE" == "local" && -n "$LOCAL_DATABASE_URL" ]]; then
    printf 'DATABASE_URL: задан через --database-url\n'
  fi
  printf '\n'
}

pause() {
  read -r -p "Нажмите Enter, чтобы вернуться в меню..." _
}

ask_required() {
  local prompt="$1"
  local value=""
  while [[ -z "$value" ]]; do
    read -r -p "$prompt" value
    value="${value#${value%%[![:space:]]*}}"
    value="${value%${value##*[![:space:]]}}"
    if [[ -z "$value" ]]; then
      printf 'Значение не может быть пустым.\n' >&2
    fi
  done
  printf '%s' "$value"
}

confirm_yes() {
  local prompt="$1"
  local answer=""
  read -r -p "$prompt [y/N]: " answer
  [[ "$answer" == "y" || "$answer" == "Y" || "$answer" == "yes" || "$answer" == "YES" || "$answer" == "да" || "$answer" == "Да" ]]
}

run_bot_command() {
  if [[ "$RUN_MODE" == "docker" ]]; then
    docker compose run --rm bot python -m "$@"
    return
  fi

  local module="$1"
  shift
  if [[ -n "$LOCAL_DATABASE_URL" ]]; then
    python -m "$module" --database-url "$LOCAL_DATABASE_URL" "$@"
  else
    python -m "$module" "$@"
  fi
}

run_seed_command() {
  local questions_path="$1"

  if [[ "$RUN_MODE" == "docker" ]]; then
    if [[ -f "$questions_path" ]]; then
      local questions_dir=""
      local questions_file=""
      questions_dir="$(cd "$(dirname "$questions_path")" && pwd)"
      questions_file="$(basename "$questions_path")"
      docker compose run --rm \
        -v "$questions_dir:/tmp/quiz-menu/questions:ro" \
        bot python -m app.seed "/tmp/quiz-menu/questions/$questions_file"
    else
      printf 'Файл не найден на хосте: %s\n' "$questions_path" >&2
      printf 'Если путь существует только внутри контейнера, запустите команду вручную: docker compose run --rm bot python -m app.seed "%s"\n' "$questions_path" >&2
      return 1
    fi
    return
  fi

  if [[ -n "$LOCAL_DATABASE_URL" ]]; then
    python -m app.seed --database-url "$LOCAL_DATABASE_URL" "$questions_path"
  else
    python -m app.seed "$questions_path"
  fi
}

configure_mode() {
  while true; do
    print_header
    printf '1) Docker Compose (рекомендуется)\n'
    printf '2) Локальный Python\n'
    printf '0) Назад\n'
    read -r -p 'Выберите режим: ' choice
    case "$choice" in
      1)
        RUN_MODE="docker"
        LOCAL_DATABASE_URL=""
        return
        ;;
      2)
        RUN_MODE="local"
        read -r -p 'DATABASE_URL для локального запуска (Enter — взять из окружения или .env): ' LOCAL_DATABASE_URL
        return
        ;;
      0) return ;;
      *) printf 'Неизвестный пункт меню.\n' >&2 ;;
    esac
  done
}

load_questions() {
  local questions_path=""
  questions_path="$(ask_required 'Укажите путь к JSON-файлу с вопросами: ')"
  run_seed_command "$questions_path"
}

show_report() {
  local report=""
  local format="table"
  while true; do
    print_header
    printf '1) Все попытки\n'
    printf '2) Все ответы\n'
    printf '3) Победители\n'
    printf '0) Назад\n'
    read -r -p 'Выберите отчёт: ' choice
    case "$choice" in
      1) report="attempts"; break ;;
      2) report="answers"; break ;;
      3) report="winners"; break ;;
      0) return ;;
      *) printf 'Неизвестный пункт меню.\n' >&2 ;;
    esac
  done

  read -r -p 'Формат csv? По умолчанию table [y/N]: ' csv_answer
  if [[ "$csv_answer" == "y" || "$csv_answer" == "Y" || "$csv_answer" == "yes" || "$csv_answer" == "YES" ]]; then
    format="csv"
  fi
  run_bot_command app.report "$report" --format "$format"
}

reset_database_menu() {
  local args=("reset-db" "--yes")
  if confirm_yes 'Удалить также вопросы и варианты ответов?'; then
    args=("reset-db" "--with-questions" "--yes")
  fi

  if confirm_yes 'Подтвердите очистку базы квиза'; then
    run_bot_command app.maintenance "${args[@]}"
  else
    printf 'Очистка отменена.\n'
  fi
}

allow_users_menu() {
  while true; do
    print_header
    printf 'Управление списком доступа\n'
    printf '1) Показать список\n'
    printf '2) Добавить или обновить пользователя\n'
    printf '3) Удалить пользователя\n'
    printf '4) Очистить список\n'
    printf '0) Назад\n'
    read -r -p 'Выберите действие: ' choice
    case "$choice" in
      1)
        run_bot_command app.maintenance allow-users list
        pause
        ;;
      2)
        local user_id username first_name last_name note
        user_id="$(ask_required 'Telegram user ID: ')"
        read -r -p 'Username без @ (Enter — пропустить): ' username
        read -r -p 'Имя (Enter — пропустить): ' first_name
        read -r -p 'Фамилия (Enter — пропустить): ' last_name
        read -r -p 'Комментарий (Enter — пропустить): ' note
        local args=(allow-users add "$user_id")
        [[ -n "$username" ]] && args+=(--username "$username")
        [[ -n "$first_name" ]] && args+=(--first-name "$first_name")
        [[ -n "$last_name" ]] && args+=(--last-name "$last_name")
        [[ -n "$note" ]] && args+=(--note "$note")
        run_bot_command app.maintenance "${args[@]}"
        pause
        ;;
      3)
        local user_id
        user_id="$(ask_required 'Telegram user ID для удаления: ')"
        run_bot_command app.maintenance allow-users remove "$user_id"
        pause
        ;;
      4)
        if confirm_yes 'Подтвердите очистку списка доступа'; then
          run_bot_command app.maintenance allow-users clear --yes
        else
          printf 'Очистка списка доступа отменена.\n'
        fi
        pause
        ;;
      0) return ;;
      *) printf 'Неизвестный пункт меню.\n' >&2 ;;
    esac
  done
}

main_menu() {
  while true; do
    print_header
    printf '1) Загрузить вопросы из JSON\n'
    printf '2) Посмотреть отчёты\n'
    printf '3) Очистить тестовые данные\n'
    printf '4) Управлять списком доступа\n'
    printf '5) Настроить режим запуска\n'
    printf '0) Выход\n'
    read -r -p 'Выберите команду: ' choice
    case "$choice" in
      1) load_questions; pause ;;
      2) show_report; pause ;;
      3) reset_database_menu; pause ;;
      4) allow_users_menu ;;
      5) configure_mode ;;
      0) printf 'Выход.\n'; exit 0 ;;
      *) printf 'Неизвестный пункт меню.\n' >&2 ;;
    esac
  done
}

main_menu
