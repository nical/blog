Title: Lyon 1.0
Date: 2022-11-2
Category: lyon, rust
Slug: lyon-1-0
Authors: Nical

I am happy to finally announce the symbolic release of `lyon 1.0.0`.


![The logo]({static}/images/lyon-logo.svg)

<p align="center">
  <a href="https://crates.io/crates/lyon">
      <img src="https://img.shields.io/crates/v/lyon.svg" alt="crates.io">
  </a>
  <a href="https://travis-ci.org/nical/lyon">
      <img src="https://img.shields.io/travis/nical/lyon/master.svg" alt="Travis Build Status">
  </a>
  <a href="https://docs.rs/lyon">
      <img src="https://docs.rs/lyon/badge.svg" alt="documentation">
  </a>
</p>

`lyon` is a Rust crate providing a number of functionalities related to vector graphics and rendering them using polygon tessellation.
The most interesting piece is the fill tessellator which produces a triangle mesh for any arbitrary vector path including shapes with holes and self intersecting ones. There are a few other note worthy goodies, such as the `lyon_geom` crate which provide a lot of useful curve manipulation math on top of `euclid`.

`lyon` first hit crates.io around mid 2016, there have been quite a few releases since then and the last release with breaking changes before `1.0.0` was in January 2021, so more than a year ago. The project is quite stable and I have been happy with the robustness of the tessellator for a while. So why not publish a `1.0.0` sooner?

For a large part I, like many in the Rust ecosystem, have been guilty of a bit of "`1.0` semver shyness" there's this irrational fear of marking something `1.0` while it isn't perfect and it's API completely figured out. The reality of software is of course that nothing is ever perfect. The other reason, the more important one, is that I've always wanted this project to grow into a fully featured 2D renderer. It was my goal at the beginning and In the process I found that making a fast and robust tessellator is a project in its own right and I got side-tracked. I think of it as a good thing, I am sure that a decent portion of lyon's users are interested in some of the difficult low level components more than in a fully flegded renderer. I haven't given up on the idea, but realistically it will be far enough in the future that the version number should reflect how I think of the pieces that I have now.

So there you have it. I'm taking this ridiculously tiny psychological leap and incrementing the major version to 1, giving me access to not two but three semver numbers to define versions. There will be a 2.0 eventually, and surely many after that.

# What's new in 1.0?

## Variable width strokes

For this release, I wanted to implement something fun. The stroke tessellator lets you specify a line width that is constant over the entire path. What if you wanted the line width to change along the path? In `lyon 0.17` you could approximate this effect by storing a line-width per endpoint using custom attributes and implementing your own `StrokeGeometryBuilder` or `StrokeVertexConstructor` to move each vertex along its normal.

```rust
// lyon 0.17.0

// We'll have a custom per-endpoint attribute in our path at index 0 to specify the width.
const STROKE_WIDTH: usize = 0;

// A custom vertex constructor for collecting the output of the stroke tessellator.
struct VariableWidthStrokeCtor;
impl StrokeVertexConstructor<Point> for VariableWidthStrokeCtor {
    fn new_vertex(&mut self, vertex: StrokeVertex) -> Point {
        // Grab the width. The tessellator automatically (and lazily) did the work of
        // interpolating the custom attributes
        let width = vertex.interpolated_attributes()[STROKE_WIDTH];
        // Instead of using `vertex.position()` compute the adjusted position manually.
        let position = vertex.position_on_path() + vertex.normal() * width;

        position
    }
}

// Create a path with one custom attribute per endpoint.
let mut builder = Path::builder_width_attributes(1);
builder.begin(point(40.0, 100.0), &[5.0]);
builder.line_to(point(80.0, 20.0), &[30.0]);
builder.cubic_bezier_to(point(100.0, 220.0), point(150.0, 50.0), point(250.0, 100.0), &[2.0]);
builder.line_to(point(200.0, 50.0), &[40.0]);
builder.end(false);

let path = builder.build();

let mut geometry: VertexBuffers<Point, u16> = VertexBuffers::new();
stroke_tessellator.tessellate_path(
    &path,
    &StrokeOptions::tolerance(0.01).with_line_caps(LineCap::Round),
    &mut BuffersBuilder::new(
        &mut geometry,
        VariableWidthStrokeCtor,
    ),
);
```

Rendering the tessellated geometry of this example would look like:

TODO: image

It works, kind of. See how the joins and caps don't look quite right? I would expect the outline to have a smoother curvature like in the image below which was rendered using lyon 1.0's built-in support for variable line width.

TODO: image



Some of the APIs have changed a bit so here is the equivalent code for lyon 1.0:


```rust
// lyon 1.0.0

// We'll have a custom per-endpoint attribute in our path at index 0 to specify the width.
const STROKE_WIDTH: AttributeIndex = 0;

// We don't really need a custom constructor now that we only output the vertex position but
// let's make one for the sake of completeness.
struct VariableWidthStrokeCtor;
impl StrokeVertexConstructor<Point> for VariableWidthStrokeCtor {
    fn new_vertex(&mut self, vertex: StrokeVertex) -> Point {
        vertex.position()
    }
}

// [...]

let mut geometry: VertexBuffers<Point, u16> = VertexBuffers::new();
stroke_tessellator.tessellate_path(
    &path,
    &StrokeOptions::tolerance(0.01)
        .with_line_caps(LineCap::Round)
        .with_variable_line_width(STROKE_WIDTH),
    &mut BuffersBuilder::new(
        &mut geometry,
        VariableWidthStrokeCtor,
    ),
);
```

That said, there is an important shortcomings to this approach to variable line widths. The line width is interpolated very naively, using the bézier curve `t` parameter. This means that the interpolation will tend to vary more rapidly along curvier parts of the curve than around the more flat parts.

But hey, it's still fun to play with and I hope it will be useful to some. Having the option to interpolate attributes linearly (based on distance instead of the curve parameter) could be a pretty nice feature for `lyon 2.0` or some other future release if there is interest for it.

## The path sampler in lyon_algorithms

Shout out to [@Mivik](https://github.com/Mivik) for proposing and implementing this new feature. In previous versions of `lyon`, if you wanted to find a point at a certain distance along a path, you could use the `PathWalker` which goes through the path and fires callbacks at certain distances. Each time a path is walked the algorithm starts from the beginning. If you need to do  thousands of random queries on a very large path, this approach is inefficient.

The idea behind path sampling is to create an acceleration data structure, called `PathMeasurements`, the creation of which has an important up-front cost (in the same ballpark as walking the path from the beginning to the end), but allows subsequent queries to be much faster than walking the path.

As a bonus the path sampler can be configured to either sample at certain distances along the path, or sample a *normalized* distances (between zero and one where one means the end of the path).

```rust
// PathMeasurements is expensive to build but easy to cache and allows the rest to be quite fast.
// It is immutable so it one it can even be used concurrently on multiple threads.
let measurements = PathMeasurements::from_path(&path, tolerance);
// PathSampler is a bit more temporary in the sense that it has a lifetime and has some mutable state.
let mut sampler = measurements.create_sampler(&path, SampleType::Normalized);
// Let's build a path as a sub-range of the original one:
let mut builder = Path::builder();
sampler.split_range(0.5..1.0, &mut builder);
let second_half = builder.build();
// And, of course, we can sample the path.
let sample = sampler.sample(0.5);
println!("mid-point: {:?}, {:?}, {:?}", sample.position(), sample.tangent(), sample.attributes());
```

## Lots of new goodies in lyon_geom

In no particular order:

 - Helpers to modify quadratic and cubic bézier curves by dragging any point on the curve.
 - Faster and more precise bézier curve length computation (once again implementing [Raph Levien's fantastic research work](https://raphlinus.github.io/curves/2018/12/28/bezier-arclength.html)).
 - A few helpers to split bézier curves into x and y-monotonic sub-curves.
 - Added `LineSegment::closest_point`/`distance_to_point`.
 - Added `QuadraticBezierSegment::closest_point`/`distance_to_point`.

## Miscellaneous other new features
 - A helper to invert the triangle winding produced by the tessellators.
 - A function to determine whether a path is shaped like an axis aligned rectangle.
 - `Path::reversed` is now implemented as an iterator.


# Notable API changes

The rest of this post goes into some nitty gritty API details. It is probably not a particularly interesting read unless you are using some of `lyon`'s advanced features. You have been warned.

## The `PathBuilder` API now includes custom attributes.

I did my best to avoid changing the whole API with this one, so it will hopefully not affect most users, unless they use or implement the `PathBuilder` trait manually.

So what are custom attributes anyway? Custom attributes, also called "interpolated attributes" in some places, are a fixed number of `f32` values that can optionally associated with each endpoint in a path. They can be used to represent various things, such as our varying line width example above, colors, or whatever can be linearly interpolated between endpoints. The fill and stroke tessellators provide access to them when creating vertices and lazily interpolate them if needed for vertices that are along a curve or at the intersection between edges.

One of my motivations with `lyon 1.0` was to get custom attributes better integrated with the various path manipulation abstractions and adapters. If a path data structure implements the `PathBuilder` trait, it automatically gets access to some generic functionalities such as flattening curves into line segments, applying transforms and other goodies. Before 1.0 `PathBuilder` methods used to not take custom attributes, so all of the generic adapters were only available to paths without attributes.

```rust
// With lyon 0.17:

// This worked. `transformed` is provided by the `PathBuilder` trait.
let mut builder_1 = Path::builder()
    .transformed(&Rotation::radians(PI / 2.0));

// This did not. The builder with attributes didn't implement `PathBuilder`.
let mut builder_2 = Path::builder_with_attributes(3)
    .transformed(&Rotation::radians(PI / 2.0));
```

In `lyon 1.0` the `PathBuilder` trait takes custom attributes so that the generic adapters can take, forward or even modify them as needed. Paths that don't accept custom attributes can still implement the `PathBuilder` trait and simply discard the attributes or assert that they are empty.

To avoid the need to explicitly pass empty attributes (`&[]` or `NO_ATTRIBUTES`) everywhere when they aren't needed, there is a `NoAttributes<Builder>` adapter that exposes the `PathBuilder` methods without the attributes parameter.

As a result:


```rust
// With lyon 1.0:

// This still works. The type of builder_1 is `NoAttributes<Transformed<BuilderImpl>>`.
let mut builder_1 = Path::builder()
    .transformed(&Rotation::radians(PI / 2.0));

builder_1.begin(point(0.0, 0.0));
builder_1.line_to(point(10.0, 0.0));
builder_1.end(false);


// This works now. The type of builder_2 is `Transformed<BuilderWithAttributes>`.
let mut builder_2 = Path::builder_with_attributes(3)
    .transformed(&Rotation::radians(PI / 2.0));

builder_2.begin(point(0.0, 0.0), &[1.0, 2.0, 3.0];
builder_2.line_to(point(10.0, 0.0), &[4.0, 5.0, 6.0];
builder_2.end(false);
```

In addition, some algorithms built on top of `PathBuilder` such as the path walker got support for custom attributes.

```rust
let mut dots = Vec::new();
let mut walker = PathWalker::new(0.0, &RegularPattern {
    callback: &mut |event: WalkerEvent| {
        let r = event.attributes[0];
        let g = event.attributes[1];
        let b = event.attributes[2];
        let a = event.attributes[3];
        dots.push(Dot { position: event.position, r, g, b, a };

        true // Return true to continue walking along the path.
    },
    // Invoke the callback above at a regular interval of 3 units.
    interval: 3.0,
});

let red = &[1.0, 0.0, 0.0, 1.0];
let blue = &[0.0, 0.0, 1.0, 1.0];
// Start with some red dots...
walker.begin(point(0.0), red);
// And end with blue ones. The dots in between will be have their color
// automatically interpolated between red and blue.
walker.quadratic_bezier_to(point(100.0, 0.0), point(100.0, 50.0), blue);
walker.end(false);
```

## New SVG path syntax parser

The SVG path syntax parser which was optionally available in the `lyon_svg` crate was re-implemented in the `lyon_extra` crate. The new parser supports a superset of the SVG path syntax in order to support specifying custom attributes. The syntax is the same with one exception: after each endpoint the following sequence of N numbers are parsed as the attributes of the endpoint.

For example with two custom attributes, `M 0 0 1 2 Q 10 0 11 5 3 4` is equivalent to the standard SVG path `M 0 0 Q 10 0 11 5` where the endpoint at position `(0, 0)` has attributes `[1, 2]` and the endpoint `(11, 5)` has attributes `[3, 4]`. Note that control points cannot have custom attributes.

You can give it a try in the command line app in the `cli` folder of the repository:

```bash
# Display a stroked path with a single custom attribute (attribute index 0) interpreted as the variable line width multiplier.
cargo run -- show "M 40 100 5 80 20 30 C 100 220 150 50 250 100 2 L 200 50 40" -s --line-cap Round --line-join Round --custom-attributes 1 --variable-line-width 0
```



## `Side::Left`/`Side::Right` renamed into `Side::Positive`/`Side::Negative`.

This change was pretty significant internally, but will only affect users of `StrokeVertex::side`.

This enum is used to indicate on which side a point is along a stroked path. The side is determined using the sign of the cross product between and edge's tangent and a vector between the edge and the point in consideration. If the cross product is positive, we are on the left side... wait is it the right side? Well it depends on whether your y axis points up or down. Lyon's tessellators don't know or need to know about that. A possibility could have been to standardize on the y-down convention like most vector graphics packages, but it was a source of confusion and bugs. The new terminology, while less evocative, is unambiguous and less error prone. As a bonus `lyon_tessellation` doesn't get dictate or contradict its users conception of what is up and down which I think is a good thing.



# Spring cleaning

In this release I removed a number of redundant or half-baked features that I felt was either not needed anynore, or wouldn't receive proper attention:

 - Bindings for the libtess2 tessellator (The `lyon_tess2` crate) which could be enabled with the `tess2` cargo feature and provide an alternative tessellator. I originally maintained a wrapper in order to have something to compare lyon against and as an alternative for users running into issues. Since then the fill tessellator has matured enough that I don't think keeping the libtess2 alternative is worth the effort anymore.
 - The path splitter, which was fun but buggy. I never had the time/energy/motivation to grow into a robust implementation.
 - The `Monotonic<T>` wrapper in `lyon_geom`.
 - The `lyon_svg` crate (the path parser moved to `lyon_extra`).
 - `lyon_extra` had a buggy software rasterizer that I had intended to use for testing but never got to working properly.

I suspect that most of the removed features had little to no users. If you depended on one of them, I suggest copying their implementation from `lyon 0.17` in your code.

These removals relieve some maintenance burden and bring the whole package to a more consistent level of quality and robustness. Some of the half-baked parts contributed to my mental block around calling it a 1.0.


# Conclusion

`lyon 1.0.0` wasn't as big a release as, say, `0.15.0` in which the fill tessellator was rewritten. It isn't the end of a cycle or the beginning of one, it is simply time to do a bit of cleanup and mark the symbolic `1.0` to reflect that the project is fairly stable.

I did rewrite the stroke tessellator to introduce the fancy variable width feature. That means there's realistically a bit of risk there of new bugs. I encourage you all to report them and I will do my best to fix them quickly.

There are a number of lyon-related things I would like to do next some of which are venturing away from tessellated triangle meshes. I don't want to tease them out too soon as it may be a while before I get them into a workable state. Stay tuned!


This symbolic milestone is as good a time as any to thank all of the people who contributed in small or in big ways to the project. So in chronological order, many thanks to:

* [Thomas (@UrbanSolution)](https://github.com/UrbanSolution/)
* [Evgeniy Reizner (@RazrFalcon)](https://github.com/RazrFalcon)
* [Jeremy Lempereur (@o0Ignition0o)](https://github.com/o0Ignition0o)
* [Emilio Cobos Álvarez (@emilio)](https://github.com/emilio)
* [@icefoxen](https://github.com/icefoxen)
* [James Kominick (@jaemk)](https://github.com/jaemk)
* [@dowoncha](https://github.com/dowoncha)
* [@nivkner](https://github.com/nivkner)
* [@kuxv](https://github.com/kuxv)
* [Karl Hobley (@kaedroho)](https://github.com/kaedroho)
* [@Noxivs](https://github.com/Noxivs)
* [Anna Liao (@anna-liao)](https://github.com/anna-liao)
* [@EloD10](https://github.com/EloD10)
* [@pizzaiter](https://github.com/pizzaiter)
* [Caleb Whiting (@whmountains)](https://github.com/whmountains)
* [Kyle Bostelmann (@bostelk)](https://github.com/bostelk)
* [Orhan Balci (@orhanbalci)](https://github.com/orhanbalci)
* [Roland Kovacs (@zen3ger)](https://github.com/zen3ger)
* [Rico A. Beti (@SilentByte)](https://github.com/SilentByte)
* [@msiglreith](https://github.com/msiglreith)
* [Tom Klein (@kleintom)](https://github.com/kleintom)
* [@gralpli](https://github.com/gralpli)
* [Simon Sapin (@SimonSapin)](https://github.com/SimonSapin)
* [Jon Hardie (@hardiesoft)](https://github.com/hardiesoft)
* [Bastien (@Dollab)](https://github.com/Dollab)
* [Artur Sapek (@artursapek)](https://github.com/artursapek)
* [Aron Granberg (@HalfVoxel)](https://github.com/HalfVoxel)
* [Benjamin Bouvier (@bnjbvr)](https://github.com/bnjbvr)
* [Aleksandr Ovchinnikov (@mr1sunshine)](https://github.com/mr1sunshine)
* [Simon Hausmann (@tronical)](https://github.com/tronical)
* [Hiroaki Yutani (@yutannihilation)](https://github.com/yutannihilation)
* [Jorge Carrasco (@carrascomj)](https://github.com/carrascomj)
* [Martin Frances (@martinfrances107)](https://github.com/martinfrances107)
* [Adrian Wielgosik (@adrian17)](https://github.com/adrian17)
* [Carl Schwan (@ognarb)](https://github.com/ognarb)
* [Eduardo Sánchez Muñoz (@eduardosm)](https://github.com/eduardosm)
* [Benjamin Halsted (@halzy)](https://github.com/halzy)
* [Mike Welsh (@Herschel)](https://github.com/Herschel)
* [simens (@simensgreen)](https://github.com/simensgreen)
* [Luis Wirth (@LU15W1R7H)](https://github.com/LU15W1R7H)
* [Sébastien Wagener (@foobar27)](https://github.com/foobar27)
* [Violeta Hernández (@OfficialURL)](https://github.com/OfficialURL)
* [@gliderkite](https://github.com/gliderkite)
* [John (@notgull)](https://github.com/notgull)
* [Alex Touchet @atouchet](https://github.com/atouchet)
* [Sameer Puri (@sameer)](https://github.com/sameer)
* [@CoorFun](https://github.com/CoorFun)
* [Murty Jones (@murtyjones)](https://github.com/murtyjones)
* [Cory Forsstrom (@tarkah)](https://github.com/tarkah)
* [@Mivik](https://github.com/Mivik)

Thank y'all! You rock!




TODO: image

cargo run -- show "M 40 100 5 80 20 30 C 100 220 150 50 250 100 2 L 200 50 40" -s --line-cap Round --line-join Round --custom-attributes 1 --variable-line-width 0

cargo run -- show "M 0 0 5 L 50 0 100 100 0 5 150 0 50" -s --line-cap Round --line-join Round --custom-attributes 1 --variable-line-width 0

