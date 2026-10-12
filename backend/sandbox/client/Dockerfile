# Normal client: browses the victim's web server at a human-ish pace. Benign traffic only.
FROM alpine:3.20
RUN apk add --no-cache curl
COPY normal_traffic.sh /normal_traffic.sh
RUN chmod +x /normal_traffic.sh
CMD ["/normal_traffic.sh"]
