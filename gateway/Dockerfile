FROM ghcr.io/gnzsnz/ib-gateway:stable

# Patch jts.ini template to allow connections from any IP (Docker network)
RUN sed -i 's/TrustedIPs=127.0.0.1/TrustedIPs=0.0.0.0/' /home/ibgateway/Jts/jts.ini.tmpl
