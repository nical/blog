Title: RustFest Paris - Part 1 - Intro
Date: 2018-6-18
Category: lyon, rust
Slug: rustfest-paris-01
Authors: Nical

> RustFest organizer: "Are you ready?"
>
> Me: "Almost."
>
> (reinstalling Xorg on my laptop 20 minutes before the talk because the window manager would not start)

I gave a talk about [lyon](https://github.com/nical/lyon) at [RustFest Paris](https://paris.rustfest.eu/).

The recordings are already online, so you can watch it [here](https://app.media.ccc.de/v/rustfest18-7-vector_graphics_rendering_on_the_gpu_in_rust_with_lyon) or on [YouTube](https://www.youtube.com/watch?v=2Ng5kpDirDI&list=PL85XCvVPmGQgdqz9kz6qH3SI_hp7Zb4s1&index=7) if you prefer.

![lets talk about vector graphics svg]({filename}/images/rustfest/intro.svg)

Even though I didn't feel super good about the flow of my speech this time around, I think that the talk was well received and the last minute "let's fix my window manager" episode didn't turn into a disaster.

It motivated me to write a series of short blog posts about the content of the talk, and explain in more details the information which I was delivering in a hurry in the hope that I wouldn't blow up the talk's allocated time slice. Most of the images in this series of posts are slides from the presentation (made in SVG with Inkscape), but there will be additional content too.

 - [Part 1 - Intro](rustfest-paris-01.html)
 - [Part 2 - Path rendering challenges](rustfest-paris-02.html)
 - Part 3 - Lyon's path tessellation algorithm
 - Part 4 - Other GPU rendering approaches.

This post is the introduction of the talk, wherein I introduce vector graphics and try to get the audience somewhat excited about it. Things will get technical in the follow-up posts.

# RustFest

Before I delve into the talk, I'd like to thank the organizers for their great work on RustFest. I can only begin to imagine how stressful and exhausting it can be to organize such an event and I believe it paid off. I had a great time and I believe the other attendees did as well.


# Raster graphics and vector graphics


Before I delve into lyon, let's get the terminology straight. Raster graphics is what typically comes to mind when thinking about images: a uniform grid of pixels where the color of each pixel is specified independently. Working with uniform grids has a lot of nice properties, for example having random-access in the content of the image to sample the color at a particular point, and being able to perform complex operations that sort of rely on random access like convolution filters.


On the other hand raster images force authors to think about the resolution at which content is produced versus resolution at which it is presented (the output resolution of a screen for example), and they don't always happen to line up perfectly. So what happens when a 800x450 pixels image has to fill a 2560x1440 pixels screen? In most cases the image will look either blurrier or pixelated. At high resolutions, raster images occupy a lot of space. Image compression formats (png, jpeg and more modern successors) do their best to mitigate that in clever ways but size remains a limiting factor when dealing with large amounts of high resolution raster images, be it in terms of disk pass, or network bandwidth.

![slide raster vs vector]({filename}/images/rustfest/rstr-vctr.svg)

Fortunately, specifying 2D content pixel by pixel is not the only choice we have at our disposal. In a lot of cases we can author and distribute not the resulting image but the steps to produce it. In very broad terms this is what I refer to when talking about vector graphics.

Think of the SVG format which can be produced with Inkscape or illustrator. With vector graphics instead of specifying a grid of pixel colors you deal in terms of squares, circles, shapes, polygons, bézier curves, which you can fill and stroke with different types of patterns such as solid colors and gradients. Of course these shapes will eventually get rasterized into a raster image since that's what your screen understands, but the description of vector graphics allows to a great extent to be resolution-independent and happens to be very compact (since specifying a red square requires a small amount of data no matter how many pixels this square will eventually cover).

Beyond SVG, I consider HTML/CSS to be a vector graphics format, since it is built around the idea of describing how to display 2D content rather than specifying each pixel individually.

The little shape in the image above doesn't look like much but add many more and you can end up with complex drawings like the famous GhostScript tiger which inevitably appears in any presentation on the topic of vector graphics.

![tiger]({filename}/images/rustfest/tiger.svg)

# Vector graphics everywhere

Today graphical applications all make use of vector graphics. Fonts are almost always described with vector formats, user interfaces, just like web pages need to be described in a way that adapts to various layouts and resolutions, a problem that vector graphics lends itself to addressing naturally.

![ui slide]({filename}/images/rustfest/ui.svg)

Using a vector format to describe maps avoids spending a lot of network bandwidth on all of these pixels and lets you zoom in and out of a map without seeing a blurry mess (unless the application is unable to render the map at interactive frame rate and choses to show you a scaled version of the previous frame while it renders the new one).

![maps]({filename}/images/rustfest/map.svg)

Using vector graphics in games can be useful as well. Today, 3D and 2D games come with gigabytes of assets, a huge part of it being fairly high resolution textures. This can be very inconvenient when attempting to distribute games over the network or even just fitting the game alongside the other installed apps in a relatively small drive.
Some games could also take advantage of the resolution-independence to present content at different scales for gameplay purposes or to enhance the story telling.

![rpg]({filename}/images/rustfest/rpg.svg)

# Vector graphics at 60 frames per seconds

Turns out that rendering a screen-full of complex vector graphics at an interactive frame rate is challenging. Whether it is on a laptop or a phone, Screens tend to have a *lot* of pixels. Filling this many pixels with interesting content means a fair amount of arithmetic, and involves a lot of memory accesses. To make things worse, the drawing model for 2D content is typically based on the [painter's algorithm](https://en.wikipedia.org/wiki/Painter%27s_algorithm) which consists in drawing back to front, and this content is usually built upon many overlapping layers. Take a closer look at the tiger above to see what I mean. pixels tend to be written to many times (this is called overdraw), which amplifies the cost of rendering at a high resolution.

![screens]({filename}/images/rustfest/screen.svg)

As a result of that a lot of applications tend to consider rendering complex vector graphics to be too expensive for high frequency updates and either bake 2D content into textures before releasing the product (a lot of games do that) or architect their rendering tech around hiding this cost, for example by rendering to intermediate surfaces at a low frequency while these surfaces are composited to the screen at a higher frequency, which allows some types of animations stay at a solid 60fps (web browsers in particular do this).

# À suivre...

That's it for part one. In the next post we'll look at how games approach the problem of redrawing the entire screen with complex content at interactive frame rates. We'll see that we can take advantage of these solutions and apply them to rendering 2D vector graphics as well.
