package observability

import (
	"encoding/json"
	"io"
	"sync"
	"time"
)

// LogLevel 日志级别
type LogLevel int

const (
	DebugLevel LogLevel = iota
	InfoLevel
	WarnLevel
	ErrorLevel
)

// Logger 结构化日志
//
// 面试要点:
// - JSON 格式输出,便于日志收集 (ELK/Loki)
// - 支持 WithField/WithFields 链式调用
// - 线程安全
type Logger struct {
	mu     sync.Mutex
	output io.Writer
	level  LogLevel
	fields map[string]interface{}
}

// NewLogger 创建日志器
func NewLogger(level LogLevel, output io.Writer) *Logger {
	return &Logger{
		output: output,
		level:  level,
		fields: make(map[string]interface{}),
	}
}

// WithField 添加单个字段
func (l *Logger) WithField(key string, value interface{}) *Logger {
	newFields := make(map[string]interface{})
	for k, v := range l.fields {
		newFields[k] = v
	}
	newFields[key] = value
	return &Logger{
		output: l.output,
		level:  l.level,
		fields: newFields,
	}
}

// WithFields 添加多个字段
func (l *Logger) WithFields(fields map[string]interface{}) *Logger {
	newFields := make(map[string]interface{})
	for k, v := range l.fields {
		newFields[k] = v
	}
	for k, v := range fields {
		newFields[k] = v
	}
	return &Logger{
		output: l.output,
		level:  l.level,
		fields: newFields,
	}
}

// Info 信息日志
func (l *Logger) Info(msg string) {
	l.log(InfoLevel, msg)
}

// Error 错误日志
func (l *Logger) Error(msg string) {
	l.log(ErrorLevel, msg)
}

// Warn 警告日志
func (l *Logger) Warn(msg string) {
	l.log(WarnLevel, msg)
}

// Debug 调试日志
func (l *Logger) Debug(msg string) {
	l.log(DebugLevel, msg)
}

// log 输出日志
func (l *Logger) log(level LogLevel, msg string) {
	if level < l.level {
		return
	}

	entry := make(map[string]interface{})
	for k, v := range l.fields {
		entry[k] = v
	}
	entry["time"] = time.Now().Format(time.RFC3339)
	entry["level"] = levelString(level)
	entry["msg"] = msg

	l.mu.Lock()
	defer l.mu.Unlock()

	json.NewEncoder(l.output).Encode(entry)
}

// levelString 日志级别字符串
func levelString(level LogLevel) string {
	switch level {
	case DebugLevel:
		return "debug"
	case InfoLevel:
		return "info"
	case WarnLevel:
		return "warn"
	case ErrorLevel:
		return "error"
	default:
		return "unknown"
	}
}
