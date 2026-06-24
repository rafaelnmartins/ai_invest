# Stockgaide PWA — Fase 1 (app instalável)

Esta é a Fase 1: o site vira um app que dá pra instalar no celular/desktop,
abre em tela cheia e funciona offline (a casca). **Push notifications são a
Fase 2** — o service worker já está preparado pra isso (gancho comentado no
final do arquivo), mas ainda não está ativo.

## Arquivos e onde colocá-los no repositório do GitHub Pages

Todos vão na **raiz** do repositório `rafaelnmartins/ai_invest` (mesmo lugar do
`index.html`), mantendo exatamente estes caminhos:

```
/manifest.json
/service-worker.js
/icons/icon-192.png
/icons/icon-512.png
/icons/icon-maskable-192.png
/icons/icon-maskable-512.png
```

⚠️ Os caminhos importam. O `service-worker.js` PRECISA estar na raiz (não numa
subpasta), senão ele não consegue controlar o site inteiro.

## Editar o index.html

Abra `HTML_SNIPPET_TO_PASTE.html` e siga os 2 passos:
1. Cole as tags do bloco (1) dentro do `<head>`.
2. Cole o `<script>` do bloco (2) logo antes de `</body>`.

Ou, se preferir, me mande seu `index.html` que eu já devolvo com tudo inserido.

## Como testar

1. Suba os arquivos no GitHub Pages.
2. Abra `https://stockgaide.com` no Chrome (desktop ou Android).
3. Deve aparecer um ícone de "instalar" na barra de endereço (desktop) ou um
   aviso "Adicionar à tela inicial" (Android).
4. No iPhone (Safari): toque em Compartilhar → "Adicionar à Tela de Início".
5. Instalado, ele abre em tela cheia com o ícone de candlesticks.

## Checar se está funcionando

- Chrome DevTools → aba **Application** → **Manifest**: deve listar nome, ícones
  e sem erros.
- Em **Service Workers**: deve aparecer "activated and running".
- O **Lighthouse** (aba no DevTools) tem um audit de PWA que confirma tudo.

## Trocar os ícones (opcional)

Os ícones atuais são um placeholder (3 candlesticks). Pra usar seu logo:
gere PNGs 192×192 e 512×512, mais as versões "maskable" (com ~18% de margem de
segurança em volta do logo), e substitua os arquivos em `/icons/` mantendo os
nomes.

## Fase 2 — Push (quando você quiser)

Vai exigir: chaves VAPID, guardar as inscrições no KV do worker, um endpoint
pra registrar inscrições, e disparar o push no caminho do webhook quando chega
sinal novo. O `service-worker.js` já tem os handlers `push` e
`notificationclick` prontos (comentados) pra esse momento.
