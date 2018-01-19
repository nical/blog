Title: Introduction to lyon: 2D vector graphics rendering on the GPU in rust
Date: 2018-1-21
Category: lyon, rust

[![crate](http://meritbadge.herokuapp.com/lyon)](https://crates.io/crates/lyon)
[![doc](https://docs.rs/lyon/badge.svg)](https://docs.rs/lyon)

[Lyon](https://github.com/nical/lyon) is a side-project that I have been working on for quite a while. The goal is to play with rendering 2D vector graphics on the GPU, and it's been a lot of fun so far. I haven't talked a lot about it online (except for a couple of reddit threads a year or two ago) so I figured it would be a good topic to get this blog started.

![The logo]({filename}/images/lyon-logo.svg)

In this post I'll talk very briefly about tessellators (lyon's biggest feature) and show a few code snippets to illustrate some of the things you can do with lyon today.

## Tessellation

Path tessellation (or triangulation), in a nutshell, is taking a path (for example a [canvas](https://developer.mozilla.org/en-US/docs/Web/API/Path2D/Path2D) or [SVG](https://www.w3.org/TR/SVG/paths.html#PathData) path) and approximating it with a set of triangles (like the way we usually represent 3d models but in 2d). While the output of the tessellator is customizable, lyon is pretty much designed for generating vertex and index buffers, which anyone working with low level graphics APIs should be familiar with. As a result we obtain geometry in a format that is very easy to work with on the GPU using the same techniques used for 3D graphics.

![tessellated shape]({filename}/images/lyon-logo-tessellated.png)

## Monotone decomposition

So how do we go about tessellating a path? The three most common algorithms are [ear-clipping](https://www.geometrictools.com/Documentation/TriangulationByEarClipping.pdf), [trapezoidal decomposition](http://www0.cs.ucl.ac.uk/staff/m.slater/Teaching/CG/1997-98/Solutions/Trap/) and monotone decomposition. In lyon I went for the latter.

Traditionally this algorithm is performed in three passes over the geometry:

 - The first step is to partition the shape in non-self-intersecting shapes (usually using the [Bentley-Ottmann algorithm](https://en.wikipedia.org/wiki/Bentley%E2%80%93Ottmann_algorithm)),
 - then partition these into y-monotone shapes,
 - and finally tessellate these y-monotone shapes into triangles.

I want to come back to this in greater details in another post, but I'll just mention here that lyon's fill tessellator is a bit different from the typical implementation of monotone tessellation in the way it represents paths, and runs the steps above in single pass instead of three. Diverging from the traditional implementations seems to pay off since some [early measurements](https://github.com/nical/lyon/blob/05fc26ebcb8bf47966655b4bf741fed7f5eff3f6/bench/tess/src/main.rs#L154) show lyon to be a bit more than twice as fast as [libtess2](https://github.com/memononen/libtess2). Take this with a grain of salt, I do need to measure a much wider range of test cases before I can boast about anything, but it's encouraging and there are still a lot of low hanging fruits on the performance side of things.

## Let's look at some code

The easiest way to show off what lyon can do for you is to look at some code snippets:

```rust
extern crate lyon;
use lyon::math::point;
use lyon::path::default::Path;
use lyon::path::builder::*;
use lyon::tessellation::*;

fn main() {
    // Build a Path.
    let mut builder = Path::builder();
    builder.move_to(point(0.0, 0.0));
    builder.line_to(point(1.0, 0.0));
    builder.quadratic_bezier_to(point(2.0, 0.0), point(2.0, 1.0));
    builder.cubic_bezier_to(point(1.0, 1.0), point(0.0, 1.0), point(0.0, 0.0));
    builder.close();
    let path = builder.build();

    // Let's use our own custom vertex type instead of the default one.
    #[derive(Copy, Clone, Debug)]
    struct MyVertex { position: [f32; 2], normal: [f32; 2] };

    // Will contain the result of the tessellation.
    let mut geometry = VertexBuffers::new();

    let mut tessellator = FillTessellator::new();

    {
        // Compute the tessellation.
        tessellator.tessellate_path(
            path.path_iter(),
            &FillOptions::default(),
            &mut BuffersBuilder::new(
                &mut geometry,
                |vertex : FillVertex| {
                    MyVertex {
                        position: vertex.position.to_array(),
                        normal: vertex.normal.to_array(),
                    }
                }
            ),
        ).unwrap();
    }

    // The tessellated geometry is ready to be uploaded to the GPU.
    println!(" -- {} vertices {} indices",
        geometry.vertices.len(),
        geometry.indices.len()
    );
}
```

Et voilà! With a fairly small amount of code you can create a path and generate the vertex/index buffers that you will be able to easily render on the GPU with glium, gfx-rs, vulkano, OpenGL, or what have you.

From there to pixels on your screen, it can be very simple or very complicated, that's really up to your rendering engine. You can have a look at [the examples](https://github.com/nical/lyon/tree/master/examples) in the repository to get an idea. Lyon doesn't provide a renderering engine (yet), although it is something that I want to explore eventually.

## What else is there in lyon?

Lyon's fill tessellator is by far where most of the work went so far. But there are a bunch of other goodies too. There is a stroke tessellator that supports most SVG stroke properties (line caps, joins, etc.), and some specialized fill and stroke tessellators for common/simpler shapes (circles, rounded rectangles, convex polygons, polylines etc.).

Lyon is plit into a few crates, in a way that is transparent for people who use the main crate, but helps with taming compile times and makes it possible for people to hand-pick certain features with minimal dependencies if they wish to.

### lyon::geom

[![crate](http://meritbadge.herokuapp.com/lyon_geom)](https://crates.io/crates/lyon_geom)
[![doc](https://docs.rs/lyon_geom/badge.svg)](https://docs.rs/lyon_geom)

Lyon's [geom](https://docs.rs/lyon_geom) module implements a lot of fun math for curve and line segments in 2D (splitting, flattening, intersecting, measuring, etc.) on top of euclid.

```rust
let curve = QuadraticBezierSegment {
    from: point(0.0, 0.0),
    ctrl: point(1.0, 0.0),
    to: point(2.0, 3.0),
};

let (c1, c2) = curve.split(0.2);

let line = Line { point: point(0.0, 1.0), vector: point(3.0, 0.5) };
for intersection in curve.line_intersections(&line) {
    //...
}

curve.flattened_for_each(0.01, |point| {
    // Approximates the curve with a sequence of line segments such
    // that the approximation is never more than 0.01 away from the
    // theoretical curve.
    approximation.push(point);
});
```

If you only need this and like minimal dependencies, just do `extern crate lyon_geom;` instead of `use lyon::geom;`.

### lyon::path

[![crate](http://meritbadge.herokuapp.com/lyon_path)](https://crates.io/crates/lyon_path)
[![doc](https://docs.rs/lyon_path/badge.svg)](https://docs.rs/lyon_path)

Lyon's [path](https://docs.rs/lyon_path) module contains path-related data structures and algorithms.

```rust
use lyon::path::builder::*;

// The default builder, it supports segments, bézier curves and arcs in
// absolute coordinates
let mut builder = Path::builder();
builder.move_to(point(1.0, 1.0));
builder.line_to(point(5.0, 1.0));
builder.quadratc_bezier_to(point(2.0, 3.0), point(1.0, 1.0));
builder.close();
let path1 = builder.build();
```

```rust
// This builder offers the full set of SVG path commands, and translates
// them into absolute coordinates since the default path data structure
// doesn't support relative coordinates.
let mut builder = Path::builder().with_svg();
builder.move_to(point(0.0, 0.0));
builder.relative_line_to(vector(10.0, 0.0));
builder.smooth_relative_cubic_bezier_to(vector(3.0, 2.0), vector(1.0, 5.0));
let path2 = builder.build();
```

```rust
// This one automatically flattens the path (approximates curves with
// a sequence of line_to commands) using 0.01 as tolerance threshold
// to build the approximation.
let mut builder = Path::builder().flattened(0.01);
builder.move_to(point(0.0, 0.0));
builder.cubic_bezier_to(point(1.0, 0.0), point(2.0, 1.0), point(2.0, 2.0));
for event in path.build().path_iter() {
    match event {
        PathEvent::MoveTo(to) => { /*...*/ }
        PathEvent::LineTo(to) => { /*...*/ }
        PathEvent::Close() => { /*...*/ }
        other => { panic!("unexpected curve segment {:?}", other); }
    }
}

// These can be composed, you get the idea...
let mut builder = Path::builder().with_svg().flattened(0.01);
```

```rust
// While the builder adapters APIs provide "push"-style conversions
// between various path formats, the same kind of operations are
// provided in a "pull"-style API with iterator adapters from the
// lyon::path::iterator module.

// This path stores some curves, and the events are flattened on the
// fly by the iterator.
for event in path2.path_iter().flattened(0.01) {
    // ...
}
```

```rust
// Place some dots at a regular interval along a path.
let mut pattern = RegularPattern {
    callback: |position: Point, _tangent, _distance| {
        dots.push(position);
    },
    interval: 3.0, // Place dots 3.0 appart from one another.
};
let start_offset = 0.0;
path.path_iter().flattened(0.01).walk(start_offset, &mut pattern);
```

I would like to evolve this crate into a sort of swiss-army-knife of path manipulations, similar to the features [paperjs](https://github.com/paperjs/paper.js/) offers, for example applying boolean operations to paths, computing convex hulls, etc.

Like before, if you only want to play with paths without tessellating themyou can do `extern crate lyon_path;` instead of `use lyon::path;`.

### lyon::svg

[![crate](http://meritbadge.herokuapp.com/lyon_svg)](https://crates.io/crates/lyon_svg)
[![doc](https://docs.rs/lyon_svg/badge.svg)](https://docs.rs/lyon_svg)

This module reexports the (very good) [svgparser crate](https://docs.rs/svgparser) and uses it to provide a simple to build a path from an SVG path syntax:

```rust
let builder = Path::builder().with_svg();
let path = svg::path_utils::build_path(svg_builder, &"M 0 0 L 10 0 L 10 10 L 0 10 z");
```

### lyon_tess2

[![crate](http://meritbadge.herokuapp.com/lyon_tess2)](https://crates.io/crates/lyon_extra)
[![doc](https://docs.rs/lyon_tess2/badge.svg)](https://docs.rs/lyon_extra) -

The lyon_tess2 crate is a very recent addition. It provides an alternative fill tessellator that wraps the [libtess2](https://github.com/memononen/libtess2) C library. I use it mostly to have something to compare lyon against, but as the two tessellators don't have the exact same feature set it can be useful to others as well.

### The command-line app

The repository contains command-line application that you can use to tessellate SVG paths in your favorite terminal, render paths, flattend paths, fuzz the tessellators, find bugs, generate reduced test-cases, and maybe soon make coffee. The app could be used, for example as a tool in an art building pipeline for a game engine. It's definitely great for debugging lyon.

```bash
lyon/cli/ $ cargo run --  show -i ../assets/logo.path --fill --stroke --tolerance 0.01
```

![screenshot]({filename}/images/lyon-cli-screenshot.png)

```bash
lyon/cli/ $ cargo run --  tessellate "M 0 0 L 1 0 L 1 1 L 0 1 Z" --fill
vertices: [(0, 0), (1, 0), (0, 1), (1, 1)]
indices: [1, 0, 2, 1, 2, 3]
```

## What's next?

There are many things that I'd like to see happening in the project, and it will certainly take a long time for most of them to concretise as time is a scarse resource.

### Polish the fill tessellator

The fill tessellator has grown into something that I am quite happy about. It is not perfect, I definitely want to keep improving its robustness and finish implementing for the non-zero [fill rule](https://www.w3.org/TR/SVG/painting.html#FillRuleProperty), but it's already robust enough for many use cases. For example [ggez](http://ggez.rs), the rust crate to make good games easily, uses it to render polygons, and I know that a few other projects use it to make games and even to render openstreetmaps data.

### A new tessellator

I want to start working on a new fill tessellator optimized for curves and able to produce a resolution-independent tessellation, probably using trapezoidal partioning like [pathfinder](https://github.com/pcwalton/pathfinder). The new tessellator will work best with curves but will not be as good for polygons as a monotone tessellator, so the current tessellator is definitely here to stay.

### A high level renderer on top of lyon

This was my initial goal when the project started forever ago. As it turns out tessellation was a fascinatingly and hard topic and I decided to focus on it for a while. It would be great to play with a 2D renderer for interactive content (like games and [creative coding](https://beesandbombs.tumblr.com/)) and see what a 2D API designed for your GPU would look like (as opposed to GPU backends for APIs that were designed for CPUs a decade or two ago for static content, which is the state of most 2D APIs these days).

### Documentation

There was a big documentation push a year ago and it was worth it. Let's do this again.

### Maybe the next feature is going to be your idea

Or even your next pull request, Who knows?

## Big thanks to all contributors

Now is a good time to underline I didn't all of this work alone. I want to thank again all the [awesome individuals](https://github.com/nical/lyon/wiki/Contributors#contributors) who submitted contributions, big and small, to the project. This project is too large for a single person's spare time, and seeing people come and give a hand is the most rewarding and motivating thing. Also thanks a lot to everyone who is using lyon and reporting bugs!

Want to join the fun? Check out the [contribution guidelines](https://github.com/nical/lyon/blob/master/CONTRIBUTING.md), get started on the [easier issues](https://github.com/nical/lyon/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22), and don't hesitate to ask any question on [gitter](https://gitter.im/lyon-rs/Lobby) or irc in #rust-gamedev.
I want this project to be as fun and welcoming as possible and I would love it to be more of a team effort than a one man show. If you are running into issues contribting, [let me know](https://github.com/nical/lyon/issues/32).

![lyon stickers photo]({filename}/images/lyon-stickers.jpg)

There are lyon stickers which is the ultimate proof that the project is cool.

