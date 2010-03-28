#!/bin/sh
dbus-send --session --type=method_call --dest=com.nokia.modest --print-reply /com/nokia/modest com.nokia.modest.MailTo string:"$1"
