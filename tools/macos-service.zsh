#!/bin/zsh
# 安装到程序目录中的 .ticket-monitor-service.zsh；手动加载到当前 GUI 会话。
# plist 留在程序目录，不写入 ~/Library/LaunchAgents，因此不会登录自启。
set -eu

TM_APP_DIR="${0:A:h}"
TM_USER_ID="$(/usr/bin/id -u)"
TM_LABEL="com.bufferducky.ticketmonitor"
TM_DOMAIN="gui/$TM_USER_ID"
TM_TARGET="$TM_DOMAIN/$TM_LABEL"
TM_SERVICE_DIR="$TM_APP_DIR/.service"
TM_PLIST="$TM_SERVICE_DIR/$TM_LABEL.plist"

service_loaded() {
    /bin/launchctl print "$TM_TARGET" >/dev/null 2>&1
}

service_pid() {
    /bin/launchctl print "$TM_TARGET" 2>/dev/null |
        /usr/bin/awk '$1 == "pid" && $2 == "=" {print $3; exit}' || true
}

service_url() {
    local tm_port=""
    if [[ -f "$TM_APP_DIR/config.yaml" ]]; then
        tm_port="$(/usr/bin/awk '
            /^web:[[:space:]]*($|#)/ {in_web=1; next}
            in_web && /^[^[:space:]#]/ {in_web=0}
            in_web && /^[[:space:]]+port:[[:space:]]*[0-9]+/ {
                sub(/^[[:space:]]+port:[[:space:]]*/, ""); print int($0); exit
            }' "$TM_APP_DIR/config.yaml")"
    fi
    [[ "$tm_port" == <1-65535> ]] || tm_port=8765
    print -r -- "http://127.0.0.1:$tm_port"
}

write_service_plist() {
    /bin/mkdir -p "$TM_SERVICE_DIR" "$TM_APP_DIR/logs"
    /usr/bin/plutil -create xml1 "$TM_PLIST"
    /usr/bin/plutil -insert Label -string "$TM_LABEL" "$TM_PLIST"
    /usr/bin/plutil -insert ProgramArguments -array "$TM_PLIST"
    /usr/bin/plutil -insert ProgramArguments.0 -string "$TM_APP_DIR/TicketMonitor" "$TM_PLIST"
    /usr/bin/plutil -insert ProgramArguments.1 -string --config "$TM_PLIST"
    /usr/bin/plutil -insert ProgramArguments.2 -string "$TM_APP_DIR/config.yaml" "$TM_PLIST"
    /usr/bin/plutil -insert WorkingDirectory -string "$TM_APP_DIR" "$TM_PLIST"
    /usr/bin/plutil -insert RunAtLoad -bool true "$TM_PLIST"
    /usr/bin/plutil -insert KeepAlive -bool true "$TM_PLIST"
    /usr/bin/plutil -insert ThrottleInterval -integer 15 "$TM_PLIST"
    /usr/bin/plutil -insert ProcessType -string Interactive "$TM_PLIST"
    /usr/bin/plutil -insert EnvironmentVariables -dictionary "$TM_PLIST"
    /usr/bin/plutil -insert EnvironmentVariables.TICKET_NO_OPEN -string 1 "$TM_PLIST"
    /usr/bin/plutil -insert EnvironmentVariables.PYTHONUNBUFFERED -string 1 "$TM_PLIST"
    /usr/bin/plutil -insert StandardOutPath -string "$TM_APP_DIR/logs/background.log" "$TM_PLIST"
    /usr/bin/plutil -insert StandardErrorPath -string "$TM_APP_DIR/logs/background.log" "$TM_PLIST"
    /usr/bin/plutil -lint "$TM_PLIST" >/dev/null
}

start_service() {
    local tm_url="$(service_url)"
    if service_loaded; then
        local tm_loaded_dir="$(/bin/launchctl print "$TM_TARGET" |
            /usr/bin/awk '/^[ \t]*working directory = / {
                sub(/^[ \t]*working directory = /, ""); print; exit
            }')"
        if [[ "$tm_loaded_dir" != "$TM_APP_DIR" ]]; then
            print -u2 -- "另一个目录中的程序正在后台运行：$tm_loaded_dir"
            print -u2 -- "请先停止已有服务，再启动这个目录中的版本。"
            return 1
        fi
    fi
    if ! service_loaded; then
        [[ -x "$TM_APP_DIR/TicketMonitor" ]] || {
            print -u2 -- "找不到 TicketMonitor，请把启动脚本和完整程序放在同一目录。"
            return 1
        }
        if /usr/bin/curl --fail --silent --max-time 1 "$tm_url/" -o /dev/null 2>/dev/null; then
            print -u2 -- "地址 $tm_url 已被其它进程占用，请先停止原来的程序。"
            return 1
        fi
        write_service_plist
        /bin/launchctl bootstrap "$TM_DOMAIN" "$TM_PLIST"
    elif [[ -z "$(service_pid)" ]]; then
        /bin/launchctl kickstart "$TM_TARGET"
    fi
    local tm_pid=""
    local tm_attempt
    for tm_attempt in {1..30}; do
        tm_pid="$(service_pid)"
        if [[ -n "$tm_pid" ]] && /usr/bin/curl --fail --silent --max-time 1 \
                "$tm_url/" -o /dev/null 2>/dev/null; then
            print -- "已在后台运行（PID $tm_pid）。这个终端窗口可以关闭。"
            print -- "操作界面：$tm_url"
            [[ "${TICKET_SERVICE_NO_OPEN:-}" == 1 ]] || /usr/bin/open "$tm_url"
            return 0
        fi
        /bin/sleep 1
    done
    print -u2 -- "服务尚未就绪，请查看 $TM_APP_DIR/logs/background.log"
    return 1
}

stop_service() {
    if service_loaded; then
        local tm_pid="$(service_pid)"
        /bin/launchctl bootout "$TM_TARGET"
        if [[ -n "$tm_pid" ]]; then
            local tm_attempt
            for tm_attempt in {1..15}; do
                /bin/kill -0 "$tm_pid" 2>/dev/null || break
                /bin/sleep 1
            done
            if /bin/kill -0 "$tm_pid" 2>/dev/null; then
                print -u2 -- "服务正在退出，稍后再启动。"
                return 1
            fi
        fi
    fi
    print -- "已停止。需要运行时，双击「启动.command」。"
}

show_status() {
    local tm_pid="$(service_pid)"
    if [[ -n "$tm_pid" ]] && /bin/kill -0 "$tm_pid" 2>/dev/null; then
        print -- "状态：后台运行中（PID $tm_pid）"
        print -- "操作界面：$(service_url)"
    else
        print -- "状态：已停止"
    fi
    print -- "登录 Mac 时自动启动：关闭"
}

case "${1:-status}" in
    start) start_service ;;
    stop) stop_service ;;
    restart) stop_service; start_service ;;
    status) show_status ;;
    *) print -u2 -- "用法：$0 start|stop|restart|status"; exit 2 ;;
esac
