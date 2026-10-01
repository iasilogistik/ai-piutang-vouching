import { Hono } from 'hono';
import { generateText } from 'ai';

const app = new Hono();

app.get('/health', (c) =>
  c.json({
    status: 'ok',
    service: 'vision',
    gateway: 'vercel-ai-sdk',
  }),
);

app.get('/vision-ai-health', async (c) => {
  try {
    const result = await generateText({
      model: 'openai/gpt-5.4-mini-fast',
      prompt: 'Reply with exactly OK',
      maxRetries: 1,
    });
    return c.json({ status: 'ok', ai: result.text.trim() });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error('VISION_AI_HEALTH_ERROR', message);
    return c.json({ status: 'error', detail: message }, 502);
  }
});

app.post('/analyze', async (c) => {
  try {
    const body = await c.req.json();
    const prompt = typeof body?.prompt === 'string' ? body.prompt : '';
    const images = Array.isArray(body?.images) ? body.images.slice(0, 3) : [];
    const model =
      typeof body?.model === 'string' && body.model.trim()
        ? body.model.trim()
        : 'openai/gpt-5.4-mini-fast';

    if (!prompt || images.length === 0) {
      return c.json({ detail: 'prompt and at least one image are required' }, 400);
    }

    const content = [
      { type: 'text' as const, text: prompt },
      ...images.map((image: unknown) => ({
        type: 'image' as const,
        image: String(image),
      })),
    ];

    const result = await generateText({
      model,
      messages: [{ role: 'user', content }],
      maxRetries: 2,
    });

    return c.json({
      model,
      text: result.text,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error('VISION_SERVICE_ERROR', message);
    return c.json({ detail: message }, 502);
  }
});

export default app;
