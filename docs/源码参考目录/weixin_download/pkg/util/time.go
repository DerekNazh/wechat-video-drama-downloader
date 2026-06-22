package util

import (
	"strconv"
	"time"
)

// NowSeconds returns the current time in seconds.
func NowSeconds() int {
	return int(time.Now().Unix())
}
func NowSecondsStr() string {
	return strconv.Itoa(int(time.Now().Unix()))
}
func NowMillisStr() string {
	return strconv.Itoa(int(time.Now().UnixMilli()))
}

func TimeToSeconds(t time.Time) string {
	return strconv.Itoa(int(t.Unix()))
}

// TimeToMillis returns the timestamp in milliseconds for the given time.
func TimeToMillis(t time.Time) string {
	return strconv.Itoa(int(t.UnixMilli()))
}

// FormatTimestamp returns formatted time string (2006-01-02_15-04-05) from Unix timestamp
func FormatTimestamp(ts int) string {
	t := time.Unix(int64(ts), 0)
	return t.Format("2006-01-02_15-04-05")
}

// FormatTimestampISO returns ISO format time string (2006-01-02T15:04:05) from Unix timestamp
func FormatTimestampISO(ts int) string {
	t := time.Unix(int64(ts), 0)
	return t.Format("2006-01-02T15:04:05")
}
