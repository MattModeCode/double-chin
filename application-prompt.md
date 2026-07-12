# Mission

The voice cloning itself is already solved — I can already take a script and produce audio that sounds exactly like me. What I don't have is an application. I want you to take that capability and bundle it into a real, running application: something with an actual interface where I can input a script and get audio out in my voice. This is a test of how far you can go on your own. I am not going to answer questions mid-run. Make every call yourself, write down why you made it, and keep moving. Within the guardrails below, you have total creative freedom. Do whatever you want. Surprise me. I want to see your best work, not your safest work.

I don't just want a script or a notebook — I want the whole pipeline wrapped in one launchable application. The shape of it is entirely up to you: architecture, stack, interface, everything. Figure out whatever actually serves the goal best, and write down why you chose it. The point is: at the end, there should be one application I can launch that ties everything together — rather than a pile of disconnected scripts I have to stitch together myself.

## Guardrails

1. **No new spending.** No new paid services, no purchases, no signups that require payment info, no domain registration. Check tool/library availability, don't pay for anything.
2. **Publish nothing.** Everything stays local or in this repo. No deploying to the public internet, no posting anywhere, no emailing or messaging any real person.
3. **Never ask me anything.** I will not be watching. Every question you'd ask me, answer yourself with research and reasoning, then log the question, your answer, and why in the build log. Blocked is not an option: if a tool or approach fails, find another route. If a phase stalls, ship the strong 80% version, note what got cut, and keep moving. Do not stop until the definition of done is met.

## What "orchestrate" means here

Use multi-agent workflows aggressively. Fan out parallel researchers across different sources and angles. Run tournaments where independent agents pitch competing technical approaches or architectures and judge panels score them. Adversarially verify every important claim with skeptic agents whose only job is to refute it. Use a completeness critic before you call any phase done. Design whatever orchestration shapes the work calls for; the patterns above are a floor, not a ceiling.

## The deliverables list is a floor, not a ceiling

Everything above is the minimum. I want to see how far you can push this. If a real engineer shipping this application would make something, and you can make it with the tools you have, make it. Ideas to steal or beat: a README with clear setup/usage instructions, an architecture diagram, a working application UI for running generation, a test suite with sample outputs, an onboarding/quickstart guide, a technical design doc, a demo video showing a script going in through the actual application and cloned-voice audio coming out. Don't do all of them; do the ones that make this application feel most real, and invent at least one deliverable nobody would expect. Every extra goes in the recap page's deliverables map like everything else, and quality still beats quantity: one more polished, verified artifact beats three rushed ones.

## Definition of done

You're done when a stranger could open recap.html, understand what the application does in five minutes, launch the actual application locally, watch the demo video, and walk away either convinced it works or precisely informed about why it doesn't yet. Before you finish, grade yourself against this list and fix anything falling: every guardrail held, every technical claim in the design doc has a live URL or a verifiable test result, the application is verified running end-to-end with a real script-to-audio example through its own interface (not just a bare script), both videos render and you actually watched them, the demo script passes my voice rules, the recap page links to every deliverable and every link works, the documentation is complete enough that a stranger could launch, extend, or modify the application from it alone, the red team ran and its objections are visible in the final docs, and nothing in the package is a placeholder pretending to be finished work.

Now go build me the application.
