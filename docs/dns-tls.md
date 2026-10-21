# DNS and TLS Certificate Preparation

[한국어](dns-tls.ko.md) | [Authentication](authentication.md) | [Documentation](README.md)

**DeciFlow** reads sources and serves the UI/API; the **Laya server** and **Jev service**
provide inference. **OAuth2-Proxy** is the HTTPS entry point for browser/API access.
The current Compose deployment requires a domain and trusted TLS certificate.

This guide prepares DNS, issues a Let's Encrypt certificate with Certbot DNS-01,
and connects renewal to OAuth2-Proxy. It uses an existing authoritative BIND9 server
with RFC2136/TSIG updates. A DNS provider's supported Certbot plugin is another
issuance method; choose one method, then use the same certificate deployment steps.
Operating your own BIND9 server is not a DeciFlow requirement.

## Hosts and Example Values

| Item | Example | Responsibility |
| --- | --- | --- |
| DeciFlow / Certbot host | Linux or WSL2, repository at `/opt/deciflow` | Runs Docker, Certbot, and the renewal scheduler |
| Authoritative primary DNS | `192.0.2.53`, Ubuntu/Debian with BIND9 | Serves `example.com` and accepts restricted TXT updates |
| Public application address | `203.0.113.10` | Router/server address reached by browsers |
| Application domain | `deciflow.example.com` | Certificate name and public DNS record |
| Public origin | `https://deciflow.example.com:4443` | Browser URL and Google OAuth registration |

Replace **all** example domains, documentation-only IP addresses, repository paths,
and service names with your environment. Use supported OS/package releases; exact
Certbot/BIND versions are not project requirements. Host commands below use `sudo`.
Keep TSIG credentials and private keys outside version control; examples contain
placeholders only.

## 1. Prepare Public DNS and Reachability

On the DNS administrator's host, create an A record for `deciflow.example.com`
pointing to the application's public IPv4 address. Publish an AAAA record only if
IPv6 routing and firewall rules also reach the service. For an existing DNS zone,
preserve its delegation, SOA, NS, secondary-server, and transfer settings.

From a machine using public DNS, check:

```bash
dig NS example.com +short
dig A deciflow.example.com +short
dig AAAA deciflow.example.com +short
```

| Traffic | Required Path |
| --- | --- |
| Browser → DeciFlow | Public TCP 4443 → Docker host TCP 4443 → OP container TCP 4443 |
| Certbot → primary DNS | TCP/UDP 53, with TSIG-authenticated updates |
| ACME validation → authoritative DNS | Public DNS queries on TCP/UDP 53 |
| Certbot → Let's Encrypt | Outbound HTTPS on TCP 443 |

For a NAT deployment, forward external TCP 4443 to the Docker host's TCP 4443.
Check host/Windows firewalls too. Do not publish the UI's internal port 4000.
DNS-01 issuance does not require inbound web ports 80/443 or a running OP container;
successful issuance alone does not establish browser connectivity on 4443.
See [Let's Encrypt challenge types](https://letsencrypt.org/docs/challenge-types/#dns-01-challenge).

## 2. Configure Restricted BIND9 Updates

**On the primary DNS host**, ensure `tsig-keygen`, `named-checkconf`, `rndc`,
`nsupdate`, and `dig` are installed with the distribution's BIND utilities.
These examples use Debian/Ubuntu paths and the `bind` group; adapt them for other
distributions. The primary must already serve the delegated `example.com` zone.

For a new installation, generate a private TSIG file without printing the key.
If a dedicated key already exists, reuse it instead of overwriting it:

```bash
sudo sh -c 'umask 077; tsig-keygen -a hmac-sha256 deciflow-acme. > /etc/bind/deciflow-acme.key'
sudo chown root:bind /etc/bind/deciflow-acme.key
sudo chmod 640 /etc/bind/deciflow-acme.key
```

Add this include to the existing BIND configuration:

```text
include "/etc/bind/deciflow-acme.key";
```

Inside the existing `zone "example.com"` block, grant only the challenge TXT name:

```text
update-policy {
    grant deciflow-acme. name _acme-challenge.deciflow.example.com. TXT;
};
```

Do not replace the entire zone configuration or combine `allow-update` with
`update-policy`. Integrate the rule into an existing policy when present. Then run:

```bash
sudo named-checkconf
sudo rndc reconfig
sudo rndc zonestatus example.com
```

Confirm dynamic updates are enabled. BIND must be able to write the zone file and
create its `.jnl` journal in the containing directory. Use a distribution-approved
writable zone location and permissions for the BIND service account.

If a custom zone path is blocked by AppArmor, add narrowly scoped rules in the
local override included by the active BIND profile. For a zone under
`/etc/bind/zones`, an example is:

```text
/etc/bind/zones/ rw,
/etc/bind/zones/db.example.com rw,
/etc/bind/zones/db.example.com.jnl rwk,
```

Reload that profile after adapting the paths; do not disable AppArmor. On SELinux
hosts, use the distribution's BIND labeling/policy instead of AppArmor rules.

```bash
sudo apparmor_parser -r /etc/apparmor.d/usr.sbin.named
sudo journalctl -u bind9 -n 50 --no-pager
sudo journalctl -k -n 100 --no-pager
```

For BIND policy and writable-directory details, see the
[RFC2136 plugin guide](https://certbot-dns-rfc2136.readthedocs.io/en/stable/#sample-bind-configuration)
and [BIND configuration reference](https://bind9.readthedocs.io/en/stable/reference.html).

## 3. Prepare Certbot and Verify DNS Updates

**On the DeciFlow / Certbot host**, install Certbot and its RFC2136 plugin using
your distribution's supported installation method. On RPM-based systems whose
enabled repositories provide these packages, the command is:

```bash
sudo dnf install certbot python3-certbot-dns-rfc2136
certbot --version
certbot plugins
```

If unavailable, follow [Certbot installation](https://certbot.eff.org/instructions)
for your OS and include the matching DNS plugin. Confirm `dns-rfc2136` appears.
Install the BIND client tools for `nsupdate` and `dig` as well.

Securely copy the TSIG key file to `/etc/letsencrypt/deciflow-acme.key` on this host;
do not store it in the repository. Restrict it to root:

```bash
sudo chown root:root /etc/letsencrypt/deciflow-acme.key
sudo chmod 600 /etc/letsencrypt/deciflow-acme.key
sudo nsupdate -k /etc/letsencrypt/deciflow-acme.key
```

At the `nsupdate` prompt, enter:

```text
server 192.0.2.53
zone example.com.
update add _acme-challenge.deciflow.example.com. 60 TXT "deciflow-dns-test"
send
quit
```

Query both the primary and public DNS; if there are secondaries, check each too:

```bash
dig @192.0.2.53 TXT _acme-challenge.deciflow.example.com +short
dig TXT _acme-challenge.deciflow.example.com +short
```

Both should return the test value after propagation. Run `nsupdate` again and
remove only this test record:

```text
server 192.0.2.53
zone example.com.
update delete _acme-challenge.deciflow.example.com. TXT "deciflow-dns-test"
send
quit
```

Create `/etc/letsencrypt/dns-rfc2136.ini` on the Certbot host:

```ini
dns_rfc2136_server = 192.0.2.53
dns_rfc2136_port = 53
dns_rfc2136_name = deciflow-acme.
dns_rfc2136_secret = REPLACE_WITH_GENERATED_TSIG_SECRET
dns_rfc2136_algorithm = HMAC-SHA256
```

Use the same generated secret, without BIND's surrounding quotes or semicolon.
Keep the credentials file root-owned and mode 600:

```bash
sudo chown root:root /etc/letsencrypt/dns-rfc2136.ini
sudo chmod 600 /etc/letsencrypt/dns-rfc2136.ini
```

## 4. Issue and Deploy the Certificate

**On the Certbot host**, request the certificate and complete Certbot's initial
account/terms prompts. `--cert-name` fixes the lineage used by the commands below:

```bash
sudo certbot certonly \
  --dns-rfc2136 \
  --dns-rfc2136-credentials /etc/letsencrypt/dns-rfc2136.ini \
  --dns-rfc2136-propagation-seconds 60 \
  --cert-name deciflow.example.com \
  -d deciflow.example.com
sudo certbot certificates
```

Certbot creates/removes challenge TXT records. Increase the propagation delay if
your authoritative servers need longer. For this lineage, the public certificate
chain is `fullchain.pem` and the private key is `privkey.pem` under
`/etc/letsencrypt/live/deciflow.example.com/`. Do not pin an expiry date in scripts.

Deploy actual file contents to the repository; do not copy dangling Certbot symlinks:

```bash
cd /opt/deciflow
sudo install -d -m 755 oauth2-proxy/tls
sudo install -m 644 /etc/letsencrypt/live/deciflow.example.com/fullchain.pem oauth2-proxy/tls/fullchain.pem
sudo install -o 65532 -m 600 /etc/letsencrypt/live/deciflow.example.com/privkey.pem oauth2-proxy/tls/privkey.pem
```

UID 65532 is the user in the project's pinned OP image. The TLS directory is
excluded from Git and image builds. A renewed Certbot file does not automatically
update these deployed copies.

Continue with [Google sign-in setup](authentication.md): set
`DECIFLOW_PUBLIC_URL=https://deciflow.example.com:4443`, register the exact Google
callback including the port, and prepare the client credentials and allow list.
Then validate and start on the Docker host:

```bash
docker compose config --quiet
docker compose up -d
curl -I https://deciflow.example.com:4443/
curl -i https://deciflow.example.com:4443/api/status
```

Certificate validation must succeed; an unauthenticated main request may return
403 with the sign-in page, while `/api/status` must return 401. Check from an
external network too; testing inside the LAN does not establish that NAT works.

## 5. Automate Renewal and OP Deployment

**On the Certbot host**, verify renewal before enabling its schedule:

```bash
sudo certbot renew --cert-name deciflow.example.com --dry-run
systemctl list-unit-files '*certbot*.timer'
```

Enable the timer supplied by your package. For an RPM package providing
`certbot-renew.timer`, use the commands below; packages with `certbot.timer` use
that unit and its corresponding service instead. Use one scheduler, not both:

```bash
sudo systemctl enable --now certbot-renew.timer
systemctl status certbot-renew.timer --no-pager
systemctl list-timers certbot-renew.timer
systemctl cat certbot-renew.service
```

Confirm the service runs `certbot renew` noninteractively. If no timer exists,
configure the supported renewal scheduler for your Certbot installation.

For the same Certbot/Docker host, create the root-owned executable
`/etc/letsencrypt/renewal-hooks/deploy/deciflow-op.sh` with the following content.
Change the repository path and lineage first. The scheduler's account must have
Docker access, and `docker` must be on its PATH with the correct Docker context:

```sh
#!/bin/sh
set -eu

if [ "${RENEWED_LINEAGE:-}" != "/etc/letsencrypt/live/deciflow.example.com" ]; then
    exit 0
fi

cd /opt/deciflow
install -d -m 755 oauth2-proxy/tls
install -m 644 "$RENEWED_LINEAGE/fullchain.pem" oauth2-proxy/tls/fullchain.pem
install -o 65532 -m 600 "$RENEWED_LINEAGE/privkey.pem" oauth2-proxy/tls/privkey.pem
docker compose up -d --no-deps --force-recreate oauth2-proxy
```

```bash
sudo chown root:root /etc/letsencrypt/renewal-hooks/deploy/deciflow-op.sh
sudo chmod 700 /etc/letsencrypt/renewal-hooks/deploy/deciflow-op.sh
sudo sh -n /etc/letsencrypt/renewal-hooks/deploy/deciflow-op.sh
sudo env RENEWED_LINEAGE=/etc/letsencrypt/live/deciflow.example.com /etc/letsencrypt/renewal-hooks/deploy/deciflow-op.sh
```

The last command tests deployment with the current certificate and **recreates OP**;
browser streams disconnect briefly, while UI/Laya and background Tasks stay running.
The lineage guard skips other certificates. Certbot runs a deploy hook after a
successful renewal; an ordinary `--dry-run` does not test this hook. Do not deploy
an ACME staging certificate to the production service. See
[Certbot renewal and hooks](https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates).

If Certbot is on another host, replace the local deployment hook with your secure
certificate transfer and remote OP recreation process; the above script assumes
Certbot and Docker share a host.

## 6. Checks and Troubleshooting

```bash
sudo certbot certificates
sudo journalctl -u certbot-renew.service -n 100 --no-pager
sudo tail -n 100 /var/log/letsencrypt/letsencrypt.log
openssl s_client -connect deciflow.example.com:4443 -servername deciflow.example.com -verify_hostname deciflow.example.com -verify_return_error </dev/null
```

| Symptom | Check |
| --- | --- |
| DNS resolves incorrectly | Public A/AAAA, delegation, and every authoritative server |
| `REFUSED` / `NOTAUTH` on update | TSIG name/secret/algorithm, zone, exact TXT update policy |
| `SERVFAIL` / journal permission error | BIND logs, zone-file/directory permissions, AppArmor/SELinux denials |
| Certbot cannot find plugin | Plugin installed into the same environment as the running Certbot |
| TXT present only on primary | Secondary transfer/notification and propagation delay |
| Issuance succeeds but browser cannot connect | NAT 4443/TCP, host firewall, WSL routing, OP container state |
| OP cannot read private key | Deployed key ownership UID 65532, mode 600, readable parent directory |
| Browser still sees old certificate | Deploy hook copied renewed files and recreated OP; inspect hook logs |
| Timer inactive or no future run | Actual unit name, enabled state, scheduler logs |
| Google `redirect_uri_mismatch` | Exact HTTPS origin and callback, including :4443; see authentication guide |

On WSL2, systemd must be enabled for systemd timers. A stopped WSL distribution or
powered-off Windows host cannot execute scheduled renewals; arrange host uptime
or a Windows-scheduled WSL invocation. Also ensure the Docker engine/context is
available when the hook runs. See [WSL systemd setup](https://learn.microsoft.com/en-us/windows/wsl/systemd).

Completion means public DNS is correct, issuance and renewal dry-run succeed, a
future renewal is scheduled, the deployment hook succeeds, and external HTTPS
serves the deployed certificate with the expected sign-in/API access controls.
