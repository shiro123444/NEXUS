API_KEY=$(cat /root/Kiro-Kroxy/kiro.rs-runtime/config/api_key.txt)
CODE1=$(curl -ksS -o /tmp/api_admin_public.html -w '%{http_code}' https://api.wbuai.me/admin)
CODE2=$(curl -ksS -o /tmp/api_models_public.json -w '%{http_code}' https://api.wbuai.me/v1/models -H "x-api-key: ${API_KEY}")
CODE3=$(curl -ksS -o /tmp/portal_public.html -w '%{http_code}' https://portal.wbuai.me/)
echo "API_ADMIN_CODE=$CODE1"
echo "API_MODELS_CODE=$CODE2"
echo "PORTAL_CODE=$CODE3"
for f in /tmp/api_admin_public.html /tmp/portal_public.html; do 
    echo "## $f"
    grep -nE 'Kiro-Kroxy|Kiro API Proxy v|Kiro Admin|kiro.rs 引擎|Realtime: Planned|MCP: Planned|Plugin Hub: Planned' "$f" | head -n 20 || echo 'NO_MATCH'
done
