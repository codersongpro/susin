// 사용 방법 영상을 만든다. scenes.html 을 머리 없는 크롬으로 열고 프레임마다 찍어 ffmpeg 로 묶는다.
//
//   FFMPEG=/경로/ffmpeg node tools/video/render.js sotong
//   FFMPEG=/경로/ffmpeg node tools/video/render.js susin
//   FFMPEG=/경로/ffmpeg node tools/video/render.js intro
//
// 결과: assets/video/<이름>.mp4 (H.264, 30fps), assets/video/<이름>.jpg (포스터)
// sotong, susin 은 1280x720 에 소리가 없다. intro(랜딩페이지 첫 화면 소개 영상)는 intro.html 을
// 1920x1080 으로 찍고, intro_sound.py 가 만든 소리를 얹는다 (python3 과 numpy 가 있어야 한다).
// playwright 와 ffmpeg 가 있어야 한다. ffmpeg 는 pip 의 imageio-ffmpeg 가 주는 것을 써도 된다.
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

const playwrightPath = process.env.PLAYWRIGHT || 'playwright';
const { chromium } = require(playwrightPath);

const ROOT = path.resolve(__dirname, '..', '..');
const FPS = 30;
const POSTER_AT = { sotong: 2.6, susin: 2.6, intro: 13.9 };
const PAGES = { intro: 'intro.html' };
const SCALE = { intro: 1.5 };      // 1280x720 으로 그린 장면을 1.5배로 찍어 1920x1080
const CRF = { intro: '28' };
const SOUND = { intro: 'intro_sound.py' };

async function main() {
  const which = process.argv[2] || 'sotong';
  const ffmpeg = process.env.FFMPEG || 'ffmpeg';
  const outDir = path.join(ROOT, 'assets', 'video');
  fs.mkdirSync(outDir, { recursive: true });
  const out = path.join(outDir, `${which}.mp4`);

  const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: SCALE[which] || 1 });
  await page.goto('file://' + path.join(__dirname, PAGES[which] || 'scenes.html') + '?v=' + which);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(500);
  const total = await page.evaluate(() => window.TOTAL);

  const poster = POSTER_AT[which] || 2;
  await page.evaluate(t => window.renderAt(t), poster);
  await page.screenshot({ path: path.join(outDir, `${which}.jpg`), type: 'jpeg', quality: 86 });

  let audio = [];
  if (SOUND[which]) {
    const wav = path.join(require('os').tmpdir(), `${which}-sound.wav`);
    const made = require('child_process').spawnSync(process.env.PYTHON || 'python3',
      [path.join(__dirname, SOUND[which]), wav], { stdio: 'inherit' });
    if (made.status !== 0) throw new Error('소리를 만들지 못했습니다');
    audio = ['-i', wav, '-map', '0:v', '-map', '1:a', '-c:a', 'aac', '-b:a', '128k', '-shortest'];
  }
  const enc = spawn(ffmpeg, [
    '-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-i', '-', ...audio,
    '-c:v', 'libx264', '-preset', 'slow', '-crf', CRF[which] || '24',
    ...(SOUND[which] ? [] : ['-tune', 'stillimage']),
    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out,
  ], { stdio: ['pipe', 'inherit', 'inherit'] });

  const frames = Math.round(total * FPS);
  for (let i = 0; i < frames; i++) {
    await page.evaluate(t => window.renderAt(t), i / FPS);
    const shot = await page.screenshot({ type: 'jpeg', quality: 92 });
    if (!enc.stdin.write(shot)) await new Promise(r => enc.stdin.once('drain', r));
    if (i % 150 === 0) process.stdout.write(`${which}: ${i}/${frames}\n`);
  }
  enc.stdin.end();
  await new Promise((resolve, reject) => enc.on('close', code => (code ? reject(new Error('ffmpeg ' + code)) : resolve())));
  await browser.close();
  const size = fs.statSync(out).size;
  console.log(`${out}  ${(size / 1024 / 1024).toFixed(2)} MB  ${total.toFixed(1)} 초`);
}

main().catch(err => { console.error(err); process.exit(1); });
