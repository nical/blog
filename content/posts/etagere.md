Title: Improving texture atlas allocation in WebRender
Date: 2020-11-28
Category: webrender, rust
Slug: etagere
Authors: Nical

Lately I have been working on improving texture atlas allocation in WebRender. It isn't an outstanding technical feat, but the journey towards achieving this goal was quite pleasant. 

This is going to be a rather long and technical post. There's a shorter version of it on the mozilla gfx team blog.

The first part is about the making of guillotiere, a crate that I first released in March 2019. In the second part we'll have a look at more recent work building upon what I did with guillotiere, to improve texture memory usage in WebRender/Firefox.

In this post I'll write technical tidbits, as well as the process and how Rust and its ecosystem made this project so nice to work on (from the point of view of someone who's written a lot of C++).

# Texture atlas allocation

In order to submit work to the GPU efficiently, WebRender groups as many drawing primitives as it can into what we call batches. A batch is submitted to the GPU as a single drawing command and has a few constraints. for example a batch can only reference a fixed set of resources (such as GPU buffers and textures). So in order to group as many drawing primitives as possible in a single batch we need to place as many drawing parameters as possible in few resources. When rendering text, WebRender pre-renders the glyphs before compositing them on the screen  so this means packing as many pre-rendered glyphs as possible into a single texture, and the same applies for rendering images and various other things.

For a moment let's simplify the case of images and text and assume that it is the same problem: input images (rectangles) of various rectangular sizes that we need to pack into a larger rectangle. This is the job of the texture atlas allocator. Another common name for this is rectangle bin packing.

![Atlas allocation]({static}/images/atlas/atlas-allocation.svg)

Many in game and web development are used to packing many images into fewer assets. In most cases this can be achieved at build time Which means that the texture atlas allocator only needs to find a good layout for a fixed set of rectangles without supporting dynamic deallocation and allocation within the atlas at run time. I call this "static" atlas allocation as opposed to "dynamic" atlas allocation.

There's a lot more literature out there about static than dynamic atlas allocation. I recommend reading [*A thousand ways to pack the bin*](http://pds25.egloos.com/pds/201504/21/98/RectangleBinPack.pdf) which is a very good survey of various static packing algorithms. Dynamic atlas allocation is unfortunately more difficult to implement while keeping good run-time performance. WebRender needs to maintain texture atlases into which items are added and removed over time. In other words we don't have a way around needing dynamic atlas allocation.

# Chapter 1

A while back, WebRender had a naive implementation of the guillotine algorithm (explained in [*A thousand ways to pack the bin*](http://pds25.egloos.com/pds/201504/21/98/RectangleBinPack.pdf)). This algorithm strikes a good compromise between packing quality and implementation complexity.
The main idea behind it can be explained simply: "Maintain a list of free rectangles, find one that can hold your allocation, split the requested allocation size out of it, creating up to two additional rectangles that are added back to the free list.". There is subtlety in which free rectangle to choose and how to split it, but the overall, the algorithm is built upon reassuringly understandable concepts.

![Guillotine allocation steps]({static}/images/atlas/guillotine-alloc.svg)

Deallocation could simply consist of adding the deallocated rectangle back to the free list, but without some way to merge back neighbor free rectangles, the atlas would quickly get into a fragmented stated with a lot of small free rectangles and can't allocate larger ones anymore.

![Fragmented state]({static}/images/atlas/fragmented.svg)

To address that, WebRender's implementation would regularly do a O(n²) complexity search to find and merge neighbor free rectangles, which was very slow when dealing with thousands of items. Eventually we stopped using the  guillotine allocator in systems that needed support for deallocation, replacing it with a very simple slab allocator which I'll get back to later in this post.

I wasn't satisfied with moving to a worse allocator because of the run-time defragmentation issue, so as a side project I wrote a guillotine allocator that tracks rectangle splits in a tree in order to find neighbor free rectangle in constant instead of quadratic time. I published it in the [guillotiere](crates.io/crates/guillotiere) crate. I wrote about how it works in details in [the documentation](https://docs.rs/guillotiere/0.6.0/guillotiere/struct.AtlasAllocator.html) so I won't go over it here. I'm quite happy about how it turned out, although I haven't pushed to use it in WebRender so far, mostly because I wanted to first see evidence that it would help and I already had evidence that many other things needed to be worked on.

## Visualizing program state using SVG

guillotiere lets you dump a visualization of the atlas in SVG format.

![Guillotine allocation visualization]({static}/images/atlas/guillotine-example-1.svg)


The image above shows the state of the atlas after a few allocations. Allocated space is represented in light blue while free space is in dark gray. It is much easier to work with than a list of coordinates in plain text. It was handy when developing and tuning the algorithm, but also when using it in other projects. While looking at the visual representation of the state animate you quickly develop an intuition of how the algorithm unfolds Concepts that are hard to explain in written form sometimes just "make sense" visually.

Dumping visual representations in a .svg file is not only a powerful tool when exploring problem some spaces, it is also surprisingly simple to do. SVG is a straightforward XML type of format which is annoying to type by hand but effortless to generate with very simple helpers. Here is how it looks using a tiny helper crate called [svg_fmt](https://crates.io/crates/svg_fmt):

```rust
    use svg_fmt::*;

    let mut output = std::fs::File::create("tmp.svg").unwrap();

    // Need this at the beginning of the file. Set the size of the drawable area to 800x600.
    writeln!(output, "{}", BeginSvg { w: 800.0, h: 600.0 })?;

    // Draw a rectangle.
    writeln!(
        output,
        r#"    {}"#,
        rectangle(10.0, 10.0, 100.0, 200.0)
            .fill(rgb(40, 40, 40))
            .stroke(Stroke::Color(black(), 1.0))
    )?;

    // Draw some text at position 100.0 100.0
    writeln!(output, "{}", text(100.0, 100.0, "Some text!".to_string()));

    // Need this at the end.
    writeln!(output, "{}", EndSvg)?;
```

So many useful visualizations can be easily built out of simple colored rectangles and text and there's other primitives provided by svg_fmt. Rectangles were all I needed in guillotiere.

You can look at [how simple the svg_fmt code is](https://github.com/nical/rust_debug/blob/492600cac47f64bcadaf9ad037ed64c5fecc8e63/svg_fmt/src/svg.rs). It has become a dependency to most of the things I've worked on lately, including WebRender which uses it to dump visualizations of texture atlases and the render graph.

![Render graph visualization]({static}/images/atlas/rendergraph.svg)

My hope by now is that if you are working on problems that can be represented in 2D space, I've managed to convince you of how easily you can supplement or break free of reading text in your debugger/terminal. If anything, just `println!(r#"<rect x="{}" y="{}" width="{}" height="{}" fill:rgb(100,0,0)" />""#, x, y, w, h);` your way into looking at your algorithms unfolding.


## Making/testing/debugging a small rust crate 

I had a great time writing guillotiere for several reasons. The problem itself had some nice properties:

 - It's a well defined problem with simple input and output data. As a result it is very easy to write unit tests and fuzz the code.
 - No nebulous design space for fancy abstractions. A retained state, query a size in, get a rectangle out. Simple.
 - Can be implemented in its own library outside of a big rendering engine, and enjoy fast compile/debug iterations.

It was the Rust programming language and ecosystem that really made it a such pleasant journey.

Bootstrapping a simple library, creating unit tests, adding dependencies is simple and effortless in Rust. This alone is a huge time saver for me compared to when I would do this sort of thing in C++ (I can only hope that the situation has improved in C++ since). Fellow Rust developers are pretty used to that so let's move on.

I quickly wrote a simple command-line application to interactively play with the packing algorithm.
The application deserializes the state of the atlas from a file, execute a command (for example allocation or deallocation) and serializes back into the file (using the .ron file format). In addition, the command-line application could dump a visualization of the atlas in SVG.

The command-line app was put together very quickly thanks to fantastic pieces of the Rust ecosystem:

 - [serde](https://crates.io/crates/serde) for serialization/deserialzation,
 - [ron](https://crates.io/crates/ron) providing a nice and readable serialized file format,
 - and [clap](https://crates.io/crates/clap) for parsing command-line arguments.

Put together, this gave me an interactive playground to test the algorithm. Playing around in a terminal would look like:

```
$ guillotiere init 1024 1024
$ guillotiere allocate 16 32
Allocated rectangle r1 of size 16x32 at origin [0, 0]
$ guillotiere allocate 200 100 --svg 01.svg
Allocated rectangle r2 of size 200x100 at origin [16, 0]
$ guillotiere deallocate r1 --svg 02.svg

etc...
```

At any time in that sequence of commands I can open the `atlas.ron` file and read the state of the atlas as if I was in a debugger, can also copy it around to save the state in a way that almost feels as powerful as using [record-and-replay debugging](https://rr-project.org/).

## Fuzzing

I mentioned fuzzing earlier. [Cargo fuzz](https://github.com/rust-fuzz/cargo-fuzz) is a joy and I really recommend using it whenever possible. It's very easy to setup, I wouldn't necessarily run it on every push, but every once in a while to find some bugs and/or get a bit of confidence about the robustness of your code. It's great. It has plenty of well written [documentation](https://rust-fuzz.github.io/book/) so I won't go into details here. I'll just mention that it's a very well made piece of Rust's ecosystem that contributes to the greatness of the whole in my opinion.

# Chapter 2

Fast forward the end of 2020. Ah 2020.

I was investigating further improvements to draw call batching and texture upload overhead which are big performance bottlenecks on low end Intel GPUs, especially on Windows.

Gathering some statistics about what causes new batches to be generated shows that it is often happening when multiple primitives use the same shader but are reading from different textures. Interesting. If we were able to pack more image into fewer textures we could improve the likelihood of primitives reading the same texture and therefore generate less batches and reduce the driver overhead.

In addition, being able to pack more images into less texture memory means we can afford to keep more of them on the GPU, evict images less often from the atlas (it is an LRU cache), and hopefully reduce the likelihood of having to re-upload images and glyphs. Texture uploads are terribly expensive on some configurations so avoiding them whenever we can is worthwhile.

Of course there is a balancing act. If we keep items longer in the cache we may not be able to pack them into fewer textures. If we pack items into few textures we may have to put pressure on the cache, not letting us keep items longer. The ideal solution will somewhere between the two. In any case, being able to pack more items in a given amount of texture space is very beneficial so more than a year after guillotiere's first release on crates.io, I had some data suggesting that better texture atlases was worth spending time on.

I was not quite at a point where I knew for sure whether integrating guillotiere into WebRender would be the right thing to do (I did have strong suspicions that it would be an improvement but I wanted to validate them first), and guillotiere might not be the best solution for WebRender's particular workloads.

## Methodology

In order to iterate quickly, I wanted to test algorithms outside of Firefox. I made a small Rust command-line program very similar to the one I had made for guillotiere (read: mostly copy-pasted from it) which I could use to replay recorded real-world atlas allocation workloads, recorded via some instrumentation in Firefox.

I ended up with a few scripts to replay the allocations different browsing sessions, that looked like:

```
#!/bin/sh
atlas allocate 7 23 -n 1
atlas allocate 10 20 -n 2
atlas allocate 15 22 -n 3
atlas allocate 14 23 -n 4
atlas allocate 19 22 -n 5
atlas allocate 5 22 -n 6
atlas allocate 15 15 -n 7
atlas deallocate 2
atlas deallocate 5

atlas svg snapshot-01.svg

atlas allocate 15 15 -n 8
# ... Tens of thousands of lines like the above.
```

I would first run the program to set some initial parameters, for example `atlas init tiled 2048 2048`, then run the scripts to replay some workloads. The scripts dumps some snapshots in SVG format at various fixed points. So that I could compare how different algorithms look at the same steps of the the same workloads.

The program would also record various stats such as size distributions, the highest number of allocated items at any given step or the amount of wasted space coming from the allocation strategy.

## The slab allocator

What replaced WebRender's guillotine allocator in the texture cache was a very simple one based on fixed power-of-two square slabs, with a few special-cased rectangular slab sizes for tall and narrow items to avoid wasting too much space. The texture is split into 512 by 512 regions, each region is split into a grid of slabs with a fixed slab size per region. 

![Slab allocation visualization]({static}/images/atlas/slab-example-1.svg)

The image above shows the slab allocator in action on the image cache for a real browsing session, replayed in my little tool.

This is a very simple scheme with very fast allocation and deallocation, however it tends to waste a lot of texture memory. For example allocating an 8x10 pixels glyph occupies a 16x16 slot, wasting more than twice the requested space. Ouch!
In addition, since regions can allocate a single slab size, space can be wasted by having a region with few allocations because the slab size happens to be uncommon.

![Slab allocation wasted space]({static}/images/atlas/slab-wasted-space.svg)

Before replacing the slab allocator, I wanted to see if simple improvements could be enough. It wouldn't be wise to replace simple code with something with more complicated without seeing how far we can push the simple solution.

## Improvements to the slab allocator

Images and glyphs used to be cached in the same textures. However we render images and glyphs with different shaders, so currently they can never be in the same rendering batches. Having a separate set of textures for images and glyphs therefore doesn't regress batching. On the other hand it provides with a few opportunities.
Not mixing images and glyphs means the glyph textures get more room for glyphs which reduces the number of textures containing glyphs overall. In other words, less chances to break batches. The same naturally applies to images. This is of course at the expense of allocating more textures on average, but it is a good trade-off for us and we are about to compensate the memory increase by using tighter packing.

In addition, glyphs and images are different types of workloads: we usually have a few hundred images of all sizes in the cache, while we have thousands of glyphs most of which have similar small sizes. Separating them allows us to introduce some simple workload-specific optimizations.

The first optimization came from noticing that glyphs are almost never larger than 128px. Having more and smaller regions, reduces the amount of atlas space that is wasted by partially empty regions, and allows us to hold more slab sizes at a given time so I reduced the region size from 512x512 to 128x128 in the glyph atlases. In the unlikely event that a glyph is larger than 128x128, it will go into the image atlas.

Next, I recorded the allocations and deallocations browsing different pages and gathered some statistics about most common glyph sizes and noticed that on a low-dpi screen, a quarter of the glyphs would land in a 16x16 slab but would have fit in a 8x16 slab. In latin scripts at least, glyphs are usually taller than wide. Adding 8x16 and 16x32 slab sizes that take advantage of this helps a *lot*.
I could have further optimized specific slab sizes by looking at the data I had collected, but the more slab sizes I would add, the higher the risk of regressing different workloads. This problem is called over-fitting. Since Firefox is used to visit content in many languages with non-latin scripts I decided that I should stick to what I considered safe bets.

![Slab allocator improvements]({static}/images/atlas/slab-improvements.svg)

The image above shows the same (real-world) workload applied to both the original and improved slab allocators.

At this point, I had nice improvements to glyph allocation using the slab allocator, but was starting to get a firm intuition that I was going to hit a ceiling trying to improve it further.

So I started playing with different algorithms. There was guillotiere to try and another atlas allocator based on the shelf packing algorithm that I had also implemented some time ago. All of these allocator have the same interface so it was very easy to put together a command-line applications (mostly copy-pasting the one I had made for guillotiere) that would allow me to run recorded workloads on each algorithms, compare the amount of memory required by each of them (and stare at some pretty visualizations).


## Shelf packing allocators

I experimented with two algorithms derived from the shelf packing allocation strategy, both of them released in the Rust crate [etagere](https://crates.io/crates/etagere). The general idea behind shelf packing  is to separate the 2-dimensional allocation problem into a 1D vertical allocator for the shelves and within each shelf, 1D horizontal allocation for the items.
The atlas is initialized with no shelf. When allocating an item, we first find the shelf that is the best fit for the item vertically, if there is none or the best fit wastes too much vertical space, we add a shelf. Once we have found or added a suitable shelf, an horizontal slice of it is used to host the allocation.

![Shelf packing]({static}/images/atlas/shelf-packing.svg)

At a glance we can see that this scheme is likely to provide much better packing than the slab allocator. For one, items are tightly packed horizontally within the shelves. That alone saves a lot of space compared to the power-of-two slab widths. Most of the waste happens vertically, between an item and the top of its shelf. How much the shelf allocator wasts vertically depends on how the shelve heights are chosen. Since we aren't constrained to power-of-two size, we can also do much better than the slab allocator vertically.

### The bucketed shelf allocator

The first shelf allocator I implemented was inspired from Mapbox's [shelf-pack](https://github.com/mapbox/shelf-pack/) allocator written in JavaScript. It has an interesting bucketing strategy: items are accumulated into fixed size "buckets" that behave like a small bump allocators. Shelves are divided into a certain number of buckets and buckets are only freed when all elements are freed. The trade-off here is to keep atlas space occupied for longer in order to reduce the CPU cost of allocating and deallocating. Only the top-most empty shelf is deallocated which can cause a bit fragmentation for long running workloads. When the atlas is full of (potentially empty) shelves the chance that a new item is too tall to fit into one of the existing shelves depends on how common the item height is. Glyphs tend to be of similar (small) heights so it works out well enough. 

I added very limited support for merging neighbor empty shelves. When an allocation fails, the atlas iterates over the shelves and checks if there is a sequence of at most three empty shelves that in total would be able to fit the requested allocation. If so, the first shelf of the sequence becomes the size of the sum, and the other shelves get a size of zero. It sounds like a band aid but the code is simple and it is working within the constraints that make the rest of the allocator very simple and fast. It's only a limited form of support for merging empty shelves and it improved the workloads that contained larger items.

![Shelf packing]({static}/images/atlas/glyphs-bucketed-shelf.svg)

The image above was generated using the command-line tool with one of the glyph cache workloads. We see fewer wide boxes rather than many thin boxes because the allocator internally doesn't keep track of each item rectangle individually, so we only see buckets filling up instead.

This allocator worked quite well for the glyph texture workloads (unsurprisingly, as Mapbox's implementation this was inspired from is used with their glyph cache). The bucketing strategy was problematic, however, with large images. The relative cost of keeping allocated space longer was higher with larger items. Especially with long running sessions, this allocator was good candidate for the glyph cache but not for the image cache.

### The simple shelf allocator

The guillotine allocator was working rather well with images. I was close to just using it for the image cache and move on. However, having spent a lot of time looking at various allocations patterns, my intuition was that we could do better. Again, this is largely thanks to being able to visualize the algorithm via these neat little SVG dumps.

It motivated experimenting with a second shelf allocator. This one is conceptually even simpler: A basic vertical 1D allocator for shelves with a basic horizontal 1D allocator per shelf. Since all items are managed individually, they are deallocated eagerly which is the main advantage over the bucketed implementation. It is also why it is slower than the bucketed allocator, especially when the number of items is high. This allocator also has full support for merging/splitting empty shelves wherever they are in the atlas.

![A glyph packing workload]({static}/images/atlas/glyphs-shelf.svg)

The image above was generated using the command-line tool with the same glyph cache workload as the previous image. This allocator tracks each individual item so we get a more precise picture. 

Unlike the Bucketed allocator, this one worked very well for the image workloads. For short workloads (visiting a handful of web pages) it was not as tightly packed as the guillotine allocator, but after browsing for longer period of time, it had a tendency to better deal with fragmentation.

![An image packing workload]({static}/images/atlas/img-shelf.svg)

The image above was generated using the command-line tool with an image cache workload. Notice how different (this is using the same 2048x2048 texture size) the image workloads look, with much fewer items and a mix of large and small items sizes.

The implementation is very simple, scanning shelves linearly and then within the selected shelf another linear scan to find a spot for the allocation. I expected performance to scale somewhat poorly with high number of glyphs (we are dealing in the thousands of glyphs which arguably isn't that high), but the performance hit wasn't as bad I had anticipated, probably helped by mostly cache friendly underlying data-structure.

### A few other experiments

For both allocators I implemented the ability to split the atlas into a fixed number of columns. Adding columns means more (smaller) shelves in the atlas, which further reduces vertical fragmentation issues, at the cost of wasting some space at the end of the shelves. The best results were obtained on 2048 by 2048 atlases with two columns. You can see in the previous two images that the shelf allocator was configured to use two columns.

The shelf allocators support arranging items in vertical shelves instead of horizontal ones. It can have an impact depending on the type of workload, for example if there is more variation in width than height for the requested allocations. As far as my testing went, it did not make a significant difference with workloads recorded in Firefox so I kept the default horizontal shelves.

The allocators also support enforcing specific alignments in x and y (effectively, rounding up the size of allocated items to a multiple of the x and y alignment). This introduces a bit of wasted space but avoids leaving tiny holes smaller than the alignment size in the atlas. Some platforms also require a certain alignment for various texture transfer operations so it is useful to have this knob to tweak at our disposal. In the Firefox integration, we use different alignments for each type of atlas, favoring small alignments for atlases that mostly contain small items to keep the relative wasted space small.

# Conclusion

![A few more texture atlases for fun]({static}/images/atlas/various-atlases.svg)

The guillotine allocator is the best at keeping track of all available space and can provide the best packing of all algorithms I tried. The shelf allocators waste a bit of space by simplifying the arrangement into shelves, and the slab allocator wastes a lot of space for the sake of simplicity. On the other hand the guillotine allocator is the slowest when dealing with multiple thousands of items and can suffer from fragmentations in some of the workloads I recorded. Overall the best compromise was the simple shelf allocator which I ended up using in Firefox for both glyph and image textures in the cache (in both cases configured to have two columns per texture). The bucketed allocator is still a very reasonable option for glyphs and we could switch to it in the future if we feel we should trade some packing efficiency for allocation/deallocation performance.

In other parts of WebRender, for short lived atlases (a single frame), the guillotine allocation algorithm is used.

These observations are mostly workload-dependent, though. Workloads are rarely completely random so results may vary.

There are other algorithms I could have explored (and maybe will someday, who knows), but I had found a satisfying compromise between simplicity, packing efficiency, and performance.

To recap, my goals were to:

 - allow packing more texture cache items into fewer textures,
 - reduce the amount of texture allocation/deallocation churn,
 - avoid increasing GPU memory usage, and if possible reduce it.

This was achieved by improving atlas packing to the point that we rarely have to allocate multiple textures for each item type (provided the amount of pixels that need to be cached which depends on what the page has to show on screen at any given time can possibly fit in a texture of course).

The results look pretty good so far. Before the changes in Firefox, glyphs would often be spread over a number of textures after having visited a couple of websites, Currently the cache eviction is set so that we rarely need more than than one or two textures with the new allocator, and with some future tuning of the cache eviction logic I am confident that we can get glyphs to fit consistently into a single texture. For images, the shelf allocator is pretty big win as well. what fit into five textures now fits into two or three.

Today this translates into fewer draw calls and less CPU-to-GPU transfers which has a noticeable impact on performance on low end Intel GPUs, in addition to reducing GPU memory usage.

The slab allocator improvements landed in [bug 1674443](https://bugzilla.mozilla.org/show_bug.cgi?id=1674443) and shipped in Firefox 85, while the shelf allocator integration work went in [bug 1679751](https://bugzilla.mozilla.org/show_bug.cgi?id=1679751) and will make it hit the release channel in Firefox 86.

The fruits of this work is packaged up in a couple of rust crates under permissive `MIT OR Apache-2.0` license:

[guillotiere](github.com/nical/guillotiere):

[![crate](https://meritbadge.herokuapp.com/guillotiere)](https://crates.io/crates/guillotiere) [![doc](https://docs.rs/guillotiere/badge.svg)](https://docs.rs/guillotiere) 

[etagere](github.com/nical/etagere):

[![crate](https://meritbadge.herokuapp.com/etagere)](https://crates.io/crates/etagere) [![doc](https://docs.rs/etagere/badge.svg)](https://docs.rs/etagere)

The hacky tool I put together to experiment with all of this can be found [on github](https://github.com/nical/texture-atlas).

I am quite happy with the Firefox improvements. I am also very pleased with the whole journey, with its visual explorations, data-driven decisions and effortless testing, debugging and even fuzzing.

