FROM ghcr.io/gnzsnz/ib-gateway:stable

# Allow API connections from any IP (needed for Docker inter-container access)
RUN sed -i 's/TrustedIPs=127.0.0.1/TrustedIPs=0.0.0.0/' /home/ibgateway/Jts/jts.ini.tmpl
