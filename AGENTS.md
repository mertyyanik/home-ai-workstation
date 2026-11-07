# Home AI Workstation — agent rules

Kullanıcıyla Türkçe iletişim kur. Önce bu dosyayı, README.md ve varsa
`work/SESSION.md` dosyasını oku. Yerel oturum notu yoksa durumu komutlarla doğrula.

## Scope and authorization

- v0.1: Windows + WSL2 Ubuntu + Docker Desktop + NVIDIA, Ollama ve Open WebUI.
- Yalnızca localhost: WebUI `127.0.0.1:3000`; Ollama `127.0.0.1:11434` (VS Code için,
  kullanıcı kararı 2026-11-07). Ollama kimlik doğrulamasızdır; LAN'a veya Tailscale'e açma.
- Kullanıcı açıkça istemedikçe Python/ML/Jupyter, Codex servis bağlantısı,
  Tailscale, uzaktan erişim veya başka fazlara geçme.
- GitHub'a push/publish, remote repo, remote veya PR oluşturma. Yerel çalışma.
- Yönetici gerektiren kurulum, BIOS/UEFI değişikliği, yeniden başlatma ve yıkıcı
  işlemler için mevcut oturumdaki izni kontrol et; izin yoksa açık onay al.
- Otomatik yeniden başlatma, volume silme, `down -v`, prune, WSL unregister,
  veri sıfırlama veya mevcut `.env`/secret üzerine yazma yapma.
- Gerçek çıktıya göre ilerle; kurulu olmak ile çalışıyor olmayı ayır.

## Repository and privacy

- ZIP'teki compose.yaml, scripts/, config/, docs/, ml/ ve CI yapısını koru.
- Tek aktif proje kopyası kullan; taşıma kararını kullanıcıyla netleştir.
- `.env`, work/, outputs/, log, model, veri ve yerel Claude ayarları Git dışıdır.
- Gerçek secret WSL içinde `~/.config/home-ai-workstation/aiws.env` dosyasındadır
  (OneDrive dışı; kullanıcı kararı 2026-11-05). İçeriğini okuma veya yazdırma.
- Secret değerlerini okuma çıktısına, sohbetlere veya raporlara yazma.
- `.gitignore` OneDrive eşitlemesini engellemez. Secret'ları bulut eşitlemesiz
  konumda üret; mevcut veriyi izinsiz taşıma veya silme.
- Docker Desktop tek daemon'dır. Ubuntu'ya ikinci Docker Engine veya Linux
  NVIDIA ekran kartı sürücüsü kurma.
- Hareketli image tag'leri donanımda doğrulandıktan sonra sabitlenecek;
  henüz test edilmemiş sürümleri doğrulanmış olarak tanıtma.

## Validation and handoff

- Önce PowerShell: `powershell -File scripts/windows-check.ps1` (bu makinede
  `pwsh` yok; PowerShell 7 varsa `pwsh` de olur).
- CLI değişikliğinde: `bash scripts/test-aiws.sh` (sahte Docker; servislere dokunmaz).
- Ubuntu hazırsa: `bash -n scripts/aiws.sh`, `bash scripts/aiws.sh doctor`,
  `bash scripts/aiws.sh gpu-test`. GPU görünürlüğü ve gerçek CUDA testi geçmeli.
- Secret oluşturmadan şema kontrolü: geçici `WEBUI_SECRET_KEY` ortam değeriyle
  `docker compose -f compose.yaml config --quiet`; gerçek config'i ekrana basma.
- Başlatma sonrası sağlık, model çıkarımı ve VRAM unload ayrı doğrulanmalı.
- Değişiklik, test, hata ve sıradaki adımları `work/SESSION.md` içinde güncelle.
  Paylaşılabilir doğrulanmış davranışı README ve docs altında tut.
