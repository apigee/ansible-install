#!/bin/bash

PASSWORD_CLASS=org.eclipse.jetty.util.security.Password
if [[ $(ls /opt/apigee/edge-gateway/lib/thirdparty/jetty-util-8*.jar 2> /dev/null) ]] ; then
    PASSWORD_CLASS=org.eclipse.jetty.http.security.Password
fi

java -cp "${APIGEE_ROOT:-/opt/apigee}/edge-gateway/lib/thirdparty/*" $PASSWORD_CLASS "$1" 2>&1 | egrep '^OBF:'
