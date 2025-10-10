# YeASTr

Yet Another AST Transformation

Yeast(r) transforms syntactic sugar.

You can't make bread/pizza without it.

This is a python only library (virtually no deps at all)

You need python>=3.12 to fully generate this library using this library,

This library will then run on python>=3.8 (except backporters)

PSFL 2.0 License (just with names changed)

### optional dependencies:
- TODO: integrate some pep8 auto-formatting tool?

## Macros - PEP638

Read https://peps.python.org/pep-0638/ up until "Specification"

Mark Shannon actually gave us the solution, I didn't realize that until now :)

Looks like then He gone crazy with a ! and $ syntax, I din't understand that.

Having CPython (and others) to implement that is sightly different.

This implementation should hopefully run on all python compilers/interpeters starting from python 3.8

### MacroPy

Seems like I missed to do proper search on the subject before starting rushing an implementation

#### That's different

Mainly in goals.

Macropy seems to be way more powerful and lisp-ish.

Our is an attempt to overcome some syntax gap and performance concerns (eg:
removing some expensive function call, backport some code)

We mainly think about macro expanded at build time.

Our import-time macro usage is a lot different. We initially used decorators to explicitly control the ordering of ast transformers, then the one ordering that worked best went hardcoded into the `build_time_transformer`.
They used import hooks and just require activation.

We try writing performant ast transformations

We don't even offer quasiquoting in our macro implementation

## PEP3136 and more

Matt Chisholm wrote a proposal for labeled break and continue statements

But it's actually the loop that gets a label.

Consider that implemented, with all the implications of such a feature.

#### outdated misleading info:
Consider that implemented (internally uses exceptions, so, may not be so performant)

By exploiting the implementation's internal you can issue a break from inside another function, getting sort of a "jump". This is kinda restricted, see yeastr-test-proj. (and like... we have some macro that gets the name of the loop upon which to call `.Break()`)

Proposal B for numerical break was the first one to be implemented, that ast manipulation also tries to squash two for loops into a genexpr if it's obvious enough it can be done; I'm thinking of removing proposal B from the codebase, let me know if I shouldn't. ... I did

#### Implicit names in loops

You got `loop_name.item` for the current element (also `.it` alias)
`loop_name.index` (also `.i`) for the current index

...additional params to For transform your For into a while...

Just look at `yeastr-test-proj/src/yeastr_test/loops.py` for examples

## Comprehensions versus Functional programming

You may want to keep writing your code in a functional style.

The downsides are:

- filter and map are slower than comprehensions

- Guido wanted to remove them (really old info (py3k made them generators))

  https://web.archive.org/web/20250118191550/https://www.artima.com/weblogs/viewpost.jsp?thread=98196

Well, with yeastr you can keep your code in the functional style

- no performance loss

- explicit equivalent function for each comprehension

  (so you don't confuse set and dict comprehesions or get confused by some expression having 3 for)

- you'd better use lambdas (again, no runtime cost)

## Backporting new features to python 3.8

You want to write your code thinking with the latest version of python

But your boss tells you it needs to run on python 2.4, ops, meant 3.8

You are forced to strip off any beautiful match you got used to, inspect f-strings for \ in parts, look for operations over dicts, change your except to use comma over as, and so on

Well, yeastr can help with that, as long as you use a new python version to backport your code before shipping it to the old python interpreter

Beware yeastr is not meant for automatic backport of existing projects. That's up to the dev who actually knows the project and it's needs.

We backported so far:

- structural pattern matching
- dict merging `|` and `|=`
- `\` in f-strings

## Examples

See yeastr-test-proj repository (SRC layout)

See yeastr-test-script repository (without any packaging or build)

yeastr can also be used "from a clone", you don't **need** to install it

But installing it is almost always a better choice. There is some difference in the usage.


## Test Suite

Currently... there is a localci.sh that does functional/integration testing

And it roughly tests the bootstrap, build, example projects build, runs every example on 3.8 and 3.13 then checks the outputs against eachother and a known 'good output' that is stored in `yeastr-test-proj` repo

So we don't have unit tests, or a python test suite, but if you break something it is really hard to get it released by mistake. mainly because of the bootstrap/build thinghy

## Type Hintings fights

If this is a project meant to make backports, then... typing is maybe bad for us.

Didn't make a strong opinion yet, need to put more thoughts together
