import { createServer } from 'vite';

async function start() {
  const server = await createServer({
    configFile: './vite.config.ts',
    server: {
      port: 5175,
      host: '127.0.0.1',
    },
  });
  await server.listen();
  console.log(`VITE_SERVER_READY: http://127.0.0.1:${server.config.server.port || 5175}`);
}

start().catch(err => {
  console.error('Failed to start Vite:', err);
  process.exit(1);
});
