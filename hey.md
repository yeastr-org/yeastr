# Hey
Can you get back to develop this?

What do you think the next steps will be?

Well, finish backporting match  <- DONE

Is backporting so much important? What's the actual goal?

There are just a few cases where backporting is useful

Usually you just upgrade.

### What doesn't play nice with this library?
- coverage reports are harder to follow or control
- IDE tools, (you're fine if you don't rely on them, but that's a niche of people)
- PEP8 checkers won't understand your code
- (Probably) The way you (user) wrote your CI and testing infrastructure needs to be adapted

### How to fix that?

Through years of development, temporary hacks and user-contributions

Are macros the main feature of this library?

Almost, it's the idea that allowed them to exists in the first place.


### Are Macros AST Transformations? or the other way around?

Nice!

### The system could have been modular, why are you shipping everything as a whole?

Sure you can use git subtrees and span several feature repos, but what's the benefit?

Just add hackpoints for the developer to add theyr own transformations.

But you're going to loose user-contributions that way...

#### I won't trust any of this if it isn't automatically tested

Well, good way of thinking, I must write tests too, as well as real world example projects

I don't think automated testing on this project can actually help

You got my point, we should first make sure the whole is properly integrated and
there is no conflict or undefined/unclear behaviour (eg: Continue over indexed For, should the counter be increased by the exception handler or not?) (of course not!, (that's not what I tought when I wrote this, but there are soe usage patterns that made it clear)

Manual testing is more appropriate until we are ready for the first pre-alpha release then automatic tests ensure we enter alpha with just bugfixes, without breaking anything

All of the examples are used as tests now

### Why should one use the new loops syntax?

Because it is meant to avoid the need of refactoring, it's a clear API.

What do you mean?

You usually start with a for, then you figure you need to enumerate, then you figure you need a while instead... it's 3 times you have to change names around and deal with index initialization, increments and so on, this distracts you from the idea your're implementing.

With yeastr, you start with a for and promote it to For when you need to, your named item doesn't need refactoring, your enumerated index have a uniform name and you never have to refactor into a while

### hey
We have already too much sparse and repetitive documentation, we should take care of it

### hey

what now?

tell me about namespacing

fine, make me a proposal...

well we implement the import hooks, and in those we analyze the ast for macros, and we namespace them automatically

idk, doesn't seem a perfect solution, how do you monkeypatch them?

what about having a ns='' parameter to `@def_macro`?

idk, everyone will inject whatever; and what's the problem? None, just...

well, how deep? just a single level? and defaults to None to be the current module?

can't we mix both proposals?

hold on... u said current module but it may be in a package or deeper...

keep namespacing short and flat (1 level) please.

This means one might need to move their macro definitions to separate files for import-time transpilation,

And then import the files that define the macros instead of the macros therein.

But also that no imports are required at all for build-time expansion...

I mean yes, but they are explicit in the build-time-transformer or in pyproject.toml

What a fight... seek for help?

#### resolution:

Ye, I implemented that 1-level namespacing... I hate it, i'm going to revert.

Let's say macros should be UPPERCASE and think of them more like C-macros that don't operate on text

I mean... you can also "jit" them through decorators, but like, it's less useful stuff?
