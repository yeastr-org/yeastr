# New ideas staging area

Hopefully answers the question: what's next?

2. `@def_macro(override=False)`
3. incremental macros

But that's the second attempt: see also hey.md

### Incremental macros

When a `@def_macro` body ends with ...

It means it wants to be expanded

So let's add a `@expand_macro` too

- expr macros should be excluded

- macros already expanded won't be affected

Suppose we want the bbt to be composed of expandable macros

you can't change it's behaviour... because it will override them

let's add a override=False to check if a macro is already defined then

dont't think that's enough, you are running inside the bbt, how can you redefine it?

come on, you can do that :3

what? couldn't get any info out of this now... what was i thinking?

I don't think it's a so wonderful idea

The next thing one would want is decorating macros...

But at that point, just grab `_macros._macros` and do your edits?

### Parallelize build pep517

Currently building just 38 and 313, because of that

### Example cross-gui-toolkit macros

But that's useless, gonna be crappy...

### Macros namespacing, import hooks, file extension

So my argument about requiring ordering in pyproject.toml is wrong:
ordering can be accomplished by importing macros

Mhh, still feels bad, what about the `with For` syntax?

How does a user define theyr own transformation and adds them to the bbt?

##### Fake macro namespaces

We wanted to have a flat dictionary of macros like so:
```py
{
    'ns0': {'macro0': ..., 'macro1': ...},
    'ns1.subns0': {'macro0': ..., 'macro1': ...},
}
```

This won't play nice with import hooks if you want to import macros and the ns doesn't exist as a module/package/ns

Rejected the idea of importing macros...

We are even more flat than that example

##### .ypy or .pyy?

.ypy

well, let's say ypy can be imported, and pyy are meant for amalgamation only?

### IMPORTANT: Make a minimal runtime with no deferred macros

Means placing a new file into the built package

You should choose the behaviour from pyproject.toml

### Where's ma shebang?

lol, there's some misconception about using python as a scripting language...

### Recursive/Nested `@def_macro`

DON'T please, don't.
