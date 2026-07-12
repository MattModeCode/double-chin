# Mission

I wanna create a mirror clone of my voice. They can provide this piece of software with a script, and it'll be able to talk exactly how I want it to in my voice. Then prove to me why it would work. This is a test of how far you can go on your own. I am not going to answer questions mid-run. Make every call yourself, write down why you made it, and keep moving. Within the guardrails below, you have total creative freedom. Do whatever you want. Surprise me. I want to see your best work, not your safest work. The only reason to stop midway is to ask me to provide actual training data to actually match my voice. When that does happen, be as specific as possible and make it as easy as possible, for instance, just flat out giving me a bunch of scripts to read and I will upload those audios.

## Guardrails

1. **No new spending.** No new paid services, no purchases, no signups that require payment info, no domain registration. Check tool/library availability, don't pay for anything.
2. **Publish nothing.** Everything stays local or in this repo. No deploying to the public internet, no posting anywhere, no emailing or messaging any real person.
3. **Never ask me anything.** I will not be watching. Every question you'd ask me, answer yourself with research and reasoning, then log the question, your answer, and why in the build log. Blocked is not an option: if a tool or approach fails, find another route. If a phase stalls, ship the strong 80% version, note what got cut, and keep moving. Do not stop until the definition of done is met.

## What "orchestrate" means here

Use multi-agent workflows aggressively. Fan out parallel researchers across different sources and angles. Run tournaments where independent agents pitch competing technical approaches or architectures and judge panels score them. Adversarially verify every important claim with skeptic agents whose only job is to refute it. Use a completeness critic before you call any phase done. Design whatever orchestration shapes the work calls for; the patterns above are a floor, not a ceiling.

## The arc

1. Hunt for the hardest technical problems (voice cloning approach, model choice, data pipeline, latency/quality tradeoffs).
2. Pick the winning approach.
3. Design the software (architecture, stack, modules, interfaces).
4. Build the brand/identity for the software (name, look, docs voice).
5. Build the thing.
6. Make the demo video.
7. Make the walkthrough/explainer video.
8. Test it.
9. Package it.

## The deliverables list is a floor, not a ceiling

Everything above is the minimum. I want to see how far you can push this. If a real engineer shipping this software would make something, and you can make it with the tools you have, make it. Ideas to steal or beat: a README with clear setup/usage instructions, an architecture diagram, a CLI or minimal UI for running it, a test suite with sample outputs, an onboarding/quickstart guide, a technical design doc, a demo video showing a script going in and cloned-voice audio coming out. Don't do all of them; do the ones that make this software feel most real, and invent at least one deliverable nobody would expect. Every extra goes in the recap page's deliverables map like everything else, and quality still beats quantity: one more polished, verified artifact beats three rushed ones.

## Definition of done

You're done when a stranger could open recap.html, understand what the software does in five minutes, run it locally, watch the demo video, and walk away either convinced it works or precisely informed about why it doesn't yet. Before you finish, grade yourself against this list and fix anything falling: every guardrail held, every technical claim in the design doc has a live URL or a verifiable test result, the software is verified running end-to-end with a real script-to-audio example, both videos render and you actually watched them, the demo script passes my voice rules, the recap page links to every deliverable and every link works, the documentation is complete enough that a stranger could extend or modify the software from it alone, the red team ran and its objections are visible in the final docs, and nothing in the package is a placeholder pretending to be finished work.

Now go build me the software.
