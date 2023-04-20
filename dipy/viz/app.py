import numpy as np

from dipy import __version__ as horizon_version
from dipy.io.stateful_tractogram import Space, StatefulTractogram
from dipy.io.streamline import save_tractogram
from dipy.tracking.streamline import Streamlines
from dipy.utils.optpkg import optional_package
from dipy.viz.gmem import GlobalHorizon
from dipy.viz.horizon.tab import (ClustersTab, PeaksTab, ROIsTab, SlicesTab,
                                  TabManager)
from dipy.viz.horizon.visualizer import ClustersVisualizer, SlicesVisualizer

fury, has_fury, setup_module = optional_package('fury')

if has_fury:
    from fury import actor, ui, window
    from fury.colormap import distinguishable_colormap

    from dipy.viz.panel import build_label, slicer_panel


HELP_MESSAGE = """
>> left click: select centroid
>> right click: see menu
>> e: expand centroids
>> r: collapse all clusters
>> h: hide unselected centroids
>> i: invert selection
>> a: select all centroids
>> s: save in file
>> y: new window
"""


class Horizon(object):

    def __init__(self, tractograms=None, images=None, pams=None, cluster=False,
                 cluster_thr=15.0, random_colors=None, length_gt=0,
                 length_lt=1000, clusters_gt=0, clusters_lt=10000,
                 world_coords=True, interactive=True, out_png='tmp.png',
                 recorded_events=None, return_showm=False, bg_color=(0, 0, 0),
                 order_transparent=True, buan=False, buan_colors=None,
                 roi_images=False, roi_colors=(1, 0, 0)):
        """Interactive medical visualization - Invert the Horizon!


        Parameters
        ----------
        tractograms : sequence of StatefulTractograms
            StatefulTractograms are used for making sure that the coordinate
            systems are correct
        images : sequence of tuples
            Each tuple contains data and affine
        pams : sequence of PeakAndMetrics
            Contains peak directions and spherical harmonic coefficients
        cluster : bool
            Enable QuickBundlesX clustering
        cluster_thr : float
            Distance threshold used for clustering. Default value 15.0 for
            small animal data you may need to use something smaller such
            as 2.0. The threshold is in mm. For this parameter to be active
            ``cluster`` should be enabled.
        random_colors : string, optional
            Given multiple tractograms and/or ROIs then each tractogram and/or
            ROI will be shown with a different color. If no value is provided,
            both the tractograms and the ROIs will have a different random
            color generated from a distinguishable colormap. If the effect
            should only be applied to one of the 2 types, then use the
            options 'tracts' and 'rois' for the tractograms and the ROIs
            respectively.
        length_gt : float
            Clusters with average length greater than ``length_gt`` amount
            in mm will be shown.
        length_lt : float
            Clusters with average length less than ``length_lt`` amount in mm
            will be shown.
        clusters_gt : int
            Clusters with size greater than ``clusters_gt`` will be shown.
        clusters_lt : int
            Clusters with size less than ``clusters_lt`` will be shown.
        world_coords : bool
            Show data in their world coordinates (not native voxel coordinates)
            Default True.
        interactive : bool
            Allow user interaction. If False then Horizon goes on stealth mode
            and just saves pictures.
        out_png : string
            Filename of saved picture.
        recorded_events : string
            File path to replay recorded events
        return_showm : bool
            Return ShowManager object. Used only at Python level. Can be used
            for extending Horizon's cababilities externally and for testing
            purposes.
        bg_color : ndarray or list or tuple
            Define the background color of the scene.
            Default is black (0, 0, 0)
        order_transparent : bool
            Default True. Use depth peeling to sort transparent objects.
            If True also enables anti-aliasing.
        buan : bool, optional
            Enables BUAN framework visualization. Default is False.
        buan_colors : list, optional
            List of colors for bundles.
        roi_images : bool, optional
            Displays binary images as contours. Default is False.
        roi_colors : ndarray or list or tuple, optional
            Define the colors of the roi images. Default is red (1, 0, 0)


        References
        ----------
        .. [Horizon_ISMRM19] Garyfallidis E., M-A. Cote, B.Q. Chandio,
            S. Fadnavis, J. Guaje, R. Aggarwal, E. St-Onge, K.S. Juneja,
            S. Koudoro, D. Reagan, DIPY Horizon: fast, modular, unified and
            adaptive visualization, Proceedings of: International Society of
            Magnetic Resonance in Medicine (ISMRM), Montreal, Canada, 2019.
        """

        self.cluster = cluster
        self.cluster_thr = cluster_thr
        self.random_colors = random_colors
        self.length_lt = length_lt
        self.length_gt = length_gt
        self.clusters_lt = clusters_lt
        self.clusters_gt = clusters_gt
        self.world_coords = world_coords
        self.interactive = interactive
        self.prng = np.random.RandomState(27)
        self.tractograms = tractograms or []
        self.out_png = out_png
        self.images = images or []
        self.pams = pams or []

        self.cea = {}  # holds centroid actors
        self.cla = {}  # holds cluster actors
        self.recorded_events = recorded_events
        self.show_m = None
        self.return_showm = return_showm
        self.bg_color = bg_color
        self.order_transparent = order_transparent
        self.buan = buan
        self.buan_colors = buan_colors
        self.roi_images = roi_images
        self.roi_colors = roi_colors

        if self.random_colors is not None:
            self.color_gen = distinguishable_colormap()
            if not self.random_colors:
                self.random_colors = ['tracts', 'rois']
        else:
            self.random_colors = []
        
        self.__clusters_visualizer = None
        self.__tabs = []
        self.__tab_mgr = None
        
        self.__select_all = False
        self.__hide_centroids = True
        
        self.__win_size = (0, 0)
    
    # TODO: Move to another class/module
    def __expand(self):
        centroid_actors = self.__clusters_visualizer.centroid_actors
        lengths = self.__clusters_visualizer.lengths
        sizes = self.__clusters_visualizer.sizes
        min_length = np.min(lengths)
        min_size = np.min(sizes)
        for cent in centroid_actors:
            if centroid_actors[cent]['selected']:
                if not centroid_actors[cent]['expanded']:
                    len_ = centroid_actors[cent]['length']
                    sz_ = centroid_actors[cent]['size']
                    if (len_ >= min_length and sz_ >= min_size):
                        centroid_actors[cent]['actor'].VisibilityOn()
                        cent.VisibilityOff()
                        centroid_actors[cent]['expanded'] = 1
        self.show_m.render()
    
    # TODO: Move to another class/module
    def __hide(self):
        centroid_actors = self.__clusters_visualizer.centroid_actors
        lengths = self.__clusters_visualizer.lengths
        sizes = self.__clusters_visualizer.sizes
        min_length = np.min(lengths)
        min_size = np.min(sizes)
        for cent in centroid_actors:
            if self.__hide_centroids:
                if (centroid_actors[cent]['length'] >= min_length or
                    centroid_actors[cent]['size'] >= min_size):
                    if centroid_actors[cent]['selected'] == 0:
                        cent.VisibilityOff()
            else:
                if (centroid_actors[cent]['length'] >= min_length and
                    centroid_actors[cent]['size'] >= min_size):
                    if centroid_actors[cent]['selected'] == 0:
                        cent.VisibilityOn()
        self.__hide_centroids = not self.__hide_centroids
        self.show_m.render()
    
    # TODO: Move to another class/module
    def __invert(self):
        centroid_actors = self.__clusters_visualizer.centroid_actors
        cluster_actors = self.__clusters_visualizer.cluster_actors
        lengths = self.__clusters_visualizer.lengths
        sizes = self.__clusters_visualizer.sizes
        min_length = np.min(lengths)
        min_size = np.min(sizes)
        for cent in centroid_actors:
            if (centroid_actors[cent]['length'] >= min_length and
                centroid_actors[cent]['size'] >= min_size):
                centroid_actors[cent]['selected'] = (
                    not centroid_actors[cent]['selected'])
                clus = centroid_actors[cent]['actor']
                cluster_actors[clus]['selected'] = (
                    centroid_actors[cent]['selected'])
        self.show_m.render()
    
    def __key_press_events(self, obj, event):
        key = obj.GetKeySym()
        # TODO: Move to another class/module
        if self.cluster:
            # retract help panel
            if key == 'o' or key == 'O':
                self.help_panel._set_position((-300, 0))
                self.show_m.render()
            if key == 'a' or key == 'A':
                self.__show_all()
            if key == 'e' or key == 'E':
                self.__expand()
            # hide on/off unselected centroids
            if key == 'h' or key == 'H':
                self.__hide()
            # invert selection
            if key == 'i' or key == 'I':
                self.__invert()
            if key == 'r' or key == 'R':
                self.__reset()
            # save current result
            if key == 's' or key == 'S':
                self.__save()
            if key == 'y' or key == 'Y':
                self.__new_window()
    
    # TODO: Move to another class/module
    def __new_window(self):
        cluster_actors = self.__clusters_visualizer.cluster_actors
        tractogram_clusters = self.__clusters_visualizer.tractogram_clusters
        active_streamlines = Streamlines()
        for bundle in cluster_actors.keys():
            if bundle.GetVisibility():
                t = cluster_actors[bundle]['tractogram']
                c = cluster_actors[bundle]['cluster']
                indices = tractogram_clusters[t][c]
                active_streamlines.extend(Streamlines(indices))

        # Using the header of the first of the tractograms
        active_sft = StatefulTractogram(
            active_streamlines, self.tractograms[0], Space.RASMM)
        hz2 = Horizon(
            [active_sft], self.images, cluster=True,
            cluster_thr=self.cluster_thr/2., random_colors=self.random_colors,
            length_lt=np.inf, length_gt=0, clusters_lt=np.inf,
            clusters_gt=0, world_coords=True, interactive=True)
        ren2 = hz2.build_scene()
        hz2.build_show(ren2)
    
    # TODO: Move to another class/module
    def __reset(self):
        centroid_actors = self.__clusters_visualizer.centroid_actors
        lengths = self.__clusters_visualizer.lengths
        sizes = self.__clusters_visualizer.sizes
        min_length = np.min(lengths)
        min_size = np.min(sizes)
        for cent in centroid_actors:
            if (centroid_actors[cent]['length'] >= min_length and
                centroid_actors[cent]['size'] >= min_size):
                centroid_actors[cent]['actor'].VisibilityOff()
                cent.VisibilityOn()
                centroid_actors[cent]['expanded'] = 0
        self.show_m.render()
    
    # TODO: Move to another class/module
    def __save(self):
        cluster_actors = self.__clusters_visualizer.cluster_actors
        tractogram_clusters = self.__clusters_visualizer.tractogram_clusters
        saving_streamlines = Streamlines()
        for bundle in cluster_actors.keys():
            if bundle.GetVisibility():
                t = cluster_actors[bundle]['tractogram']
                c = cluster_actors[bundle]['cluster']
                indices = tractogram_clusters[t][c]
                saving_streamlines.extend(Streamlines(indices))
        print('Saving result in tmp.trk')

        # Using the header of the first of the tractograms
        sft_new = StatefulTractogram(
            saving_streamlines, self.tractograms[0], Space.RASMM)
        save_tractogram(sft_new, 'tmp.trk', bbox_valid_check=False)
        print('Saved!')
    
    # TODO: Move to another class/module
    def __show_all(self):
        centroid_actors = self.__clusters_visualizer.centroid_actors
        cluster_actors = self.__clusters_visualizer.cluster_actors
        lengths = self.__clusters_visualizer.lengths
        sizes = self.__clusters_visualizer.sizes
        min_length = np.min(lengths)
        min_size = np.min(sizes)
        for cent in centroid_actors:
            if (centroid_actors[cent]['length'] >= min_length and 
                centroid_actors[cent]['size'] >= min_size):
                if not self.__select_all:
                    centroid_actors[cent]['selected'] = 1
                    self.__select_all = True
                else:
                    centroid_actors[cent]['selected'] = 0
                    self.__select_all = False
                clus = centroid_actors[cent]['actor']
                cluster_actors[clus]['selected'] = (
                    centroid_actors[cent]['selected'])
        self.show_m.render()
    
    def __win_callback(self, obj, event):
        if self.__win_size != obj.GetSize():
            size_old = self.__win_size
            self.__win_size = obj.GetSize()
            size_change = [self.__win_size[0] - size_old[0], 0]
            if len(self.__tabs) > 0:
                self.__tab_mgr.reposition(self.__win_size)
            if self.cluster:
                #self.help_panel.re_align(size_change)
                panel_size = self.help_panel._get_size()
                new_pos = self.__win_size - panel_size - 5
                self.help_panel._set_position(new_pos)

    def build_scene(self):
        self.mem = GlobalHorizon()
        scene = window.Scene()
        scene.background(self.bg_color)
        return scene

    def build_show(self, scene):
        
        title = 'Horizon ' + horizon_version
        self.show_m = window.ShowManager(
            scene, title=title, size=(1920, 1080), reset_camera=False,
            order_transparent=self.order_transparent)
        
        if len(self.tractograms) > 0:
            
            if self.cluster:
                self.__clusters_visualizer = ClustersVisualizer(
                    self.show_m, scene, self.tractograms)
            
            color_ind = 0
            
            for t, sft in enumerate(self.tractograms):
                streamlines = sft.streamlines
                
                if 'tracts' in self.random_colors:
                    colors = next(self.color_gen)
                else:
                    colors = None
                
                if not self.world_coords:
                    # TODO: Get affine from a StatefullTractogram
                    raise ValueError(
                        'Currently native coordinates are not supported for'
                        'streamlines.')
                
                if self.cluster:
                    self.__clusters_visualizer.add_cluster_actors(
                        t, streamlines, self.cluster_thr, colors)
                else:
                    if self.buan:
                        colors = self.buan_colors[color_ind]
                    
                    streamline_actor = actor.line(streamlines, colors=colors)
                    streamline_actor.GetProperty().SetEdgeVisibility(1)
                    streamline_actor.GetProperty().SetRenderLinesAsTubes(1)
                    streamline_actor.GetProperty().SetLineWidth(6)
                    streamline_actor.GetProperty().SetOpacity(1)
                    scene.add(streamline_actor)
                
                color_ind += 1

            if self.cluster:
                # Information panel
                text_block = build_label(HELP_MESSAGE, 18)
                text_block.message = HELP_MESSAGE

                self.help_panel = ui.Panel2D(
                    size=(320, 200), position=(1595, 875), color=(.8, .8, 1.),
                    opacity=.2, align='left')

                self.help_panel.add_element(text_block, coords=(0.05, 0.1))
                scene.add(self.help_panel)
                self.__tabs.append(ClustersTab(
                    self.__clusters_visualizer, self.cluster_thr))

        if len(self.images) > 0:
            # Only first non-binary image loading supported for now
            first_img = True
            if self.roi_images:
                roi_color = self.roi_colors
                roi_actors = []
                for img in self.images:
                    img_data, img_affine = img
                    dim = np.unique(img_data).shape[0]
                    if dim == 2:
                        if 'rois' in self.random_colors:
                            roi_color = next(self.color_gen)
                        roi_actor = actor.contour_from_roi(
                            img_data, affine=img_affine, color=roi_color)
                        scene.add(roi_actor)
                        roi_actors.append(roi_actor)
                    else:
                        if first_img:
                            data, affine = img
                            self.vox2ras = affine
                            slices_viz = SlicesVisualizer(
                                self.show_m.iren, scene, data, affine=affine,
                                world_coords=self.world_coords)
                            self.__tabs.append(SlicesTab(slices_viz))
                            first_img = False
                if len(roi_actors) > 0:
                    self.__tabs.append(ROIsTab(roi_actors))
            else:
                data, affine = self.images[0]
                self.vox2ras = affine
                slices_viz = SlicesVisualizer(
                    self.show_m.iren, scene, data, affine=affine,
                    world_coords=self.world_coords)
                self.__tabs.append(SlicesTab(slices_viz))
        
        if len(self.pams) > 0:
            pam = self.pams[0]
            peak_actor = actor.peak(pam.peak_dirs, affine=pam.affine)
            scene.add(peak_actor)
            self.__tabs.append(PeaksTab(peak_actor))
        
        else:
            data = None
            affine = None
            pam = None
        
        self.__win_size = scene.GetSize()
        
        if len(self.__tabs) > 0:
            self.__tab_mgr = TabManager(self.__tabs, self.__win_size)
            scene.add(self.__tab_mgr.tab_ui)

        self.show_m.initialize()

        options = [r'un\hide centroids', 'invert selection',
                   r'un\select all', 'expand clusters',
                   'collapse clusters', 'save streamlines',
                   'recluster']
        listbox = ui.ListBox2D(values=options, position=(10, 300),
                               size=(200, 270),
                               multiselection=False, font_size=18)

        def display_element():
            action = listbox.selected[0]
            if action == r'un\hide centroids':
                self.__hide()
            if action == 'invert selection':
                self.__invert()
            if action == r'un\select all':
                self.__show_all()
            if action == 'expand clusters':
                self.__expand()
            if action == 'collapse clusters':
                self.__reset()
            if action == 'save streamlines':
                self.__save()
            if action == 'recluster':
                self.__new_window()

        listbox.on_change = display_element
        listbox.panel.opacity = 0.2
        listbox.set_visibility(0)

        self.show_m.scene.add(listbox)

        def left_click_centroid_callback(obj, event):

            self.cea[obj]['selected'] = not self.cea[obj]['selected']
            self.cla[self.cea[obj]['cluster_actor']]['selected'] = \
                self.cea[obj]['selected']
            self.show_m.render()

        def right_click_centroid_callback(obj, event):
            for lactor in listbox._get_actors():
                lactor.SetVisibility(not lactor.GetVisibility())

            listbox.scroll_bar.set_visibility(False)
            self.show_m.render()

        def left_click_cluster_callback(obj, event):

            if self.cla[obj]['selected']:
                self.cla[obj]['centroid_actor'].VisibilityOn()
                ca = self.cla[obj]['centroid_actor']
                self.cea[ca]['selected'] = 0
                obj.VisibilityOff()
                self.cea[ca]['expanded'] = 0

            self.show_m.render()

        def right_click_cluster_callback(obj, event):
            print('Cluster Area Selected')
            self.show_m.render()

        for cl in self.cla:
            cl.AddObserver('LeftButtonPressEvent',
                           left_click_cluster_callback,
                           1.0)
            cl.AddObserver('RightButtonPressEvent',
                           right_click_cluster_callback,
                           1.0)
            self.cla[cl]['centroid_actor'].AddObserver(
                'LeftButtonPressEvent', left_click_centroid_callback, 1.0)
            self.cla[cl]['centroid_actor'].AddObserver(
                'RightButtonPressEvent', right_click_centroid_callback, 1.0)

        self.mem.window_timer_cnt = 0

        def timer_callback(obj, event):

            self.mem.window_timer_cnt += 1
            # TODO possibly add automatic rotation option
            # self.show_m.scene.azimuth(0.01 * self.mem.window_timer_cnt)
            # self.show_m.render()

        scene.reset_camera()
        scene.zoom(1.5)
        scene.reset_clipping_range()

        if self.interactive:

            self.show_m.add_window_callback(self.__win_callback)
            self.show_m.add_timer_callback(True, 200, timer_callback)
            self.show_m.iren.AddObserver(
                'KeyPressEvent', self.__key_press_events)

            if self.return_showm:
                return self.show_m

            if self.recorded_events is None:
                self.show_m.render()
                self.show_m.start()

            else:

                # set to True if event recorded file needs updating
                recording = False
                recording_filename = self.recorded_events

                if recording:
                    self.show_m.record_events_to_file(recording_filename)
                else:
                    self.show_m.play_events_from_file(recording_filename)

        else:

            window.record(scene, out_path=self.out_png,
                          size=(1200, 900),
                          reset_camera=False)


def horizon(tractograms=None, images=None, pams=None,
            cluster=False, cluster_thr=15.0,
            random_colors=None, bg_color=(0, 0, 0), order_transparent=True,
            length_gt=0, length_lt=1000, clusters_gt=0, clusters_lt=10000,
            world_coords=True, interactive=True, buan=False, buan_colors=None,
            roi_images=False, roi_colors=(1, 0, 0), out_png='tmp.png',
            recorded_events=None, return_showm=False):
    """Interactive medical visualization - Invert the Horizon!


    Parameters
    ----------
    tractograms : sequence of StatefulTractograms
            StatefulTractograms are used for making sure that the coordinate
            systems are correct
    images : sequence of tuples
        Each tuple contains data and affine
    pams : sequence of PeakAndMetrics
        Contains peak directions and spherical harmonic coefficients
    cluster : bool
        Enable QuickBundlesX clustering
    cluster_thr : float
        Distance threshold used for clustering. Default value 15.0 for
        small animal data you may need to use something smaller such
        as 2.0. The threshold is in mm. For this parameter to be active
        ``cluster`` should be enabled.
    random_colors : string
        Given multiple tractograms and/or ROIs then each tractogram and/or
        ROI will be shown with different color. If no value is provided both
        the tractograms and the ROIs will have a different random color
        generated from a distinguishable colormap. If the effect should only be
        applied to one of the 2 objects, then use the options 'tracts' and
        'rois' for the tractograms and the ROIs respectively.
    bg_color : ndarray or list or tuple
        Define the background color of the scene. Default is black (0, 0, 0)
    order_transparent : bool
        Default True. Use depth peeling to sort transparent objects.
        If True also enables anti-aliasing.
    length_gt : float
        Clusters with average length greater than ``length_gt`` amount
        in mm will be shown.
    length_lt : float
        Clusters with average length less than ``length_lt`` amount in mm
        will be shown.
    clusters_gt : int
        Clusters with size greater than ``clusters_gt`` will be shown.
    clusters_lt : int
        Clusters with size less than ``clusters_lt`` will be shown.
    world_coords : bool
        Show data in their world coordinates (not native voxel coordinates)
        Default True.
    interactive : bool
        Allow user interaction. If False then Horizon goes on stealth mode
        and just saves pictures.
    buan : bool, optional
        Enables BUAN framework visualization. Default is False.
    buan_colors : list, optional
        List of colors for bundles.
    roi_images : bool, optional
        Displays binary images as contours. Default is False.
    roi_colors : ndarray or list or tuple, optional
        Define the color of the roi images. Default is red (1, 0, 0)
    out_png : string
        Filename of saved picture.
    recorded_events : string
        File path to replay recorded events
    return_showm : bool
        Return ShowManager object. Used only at Python level. Can be used
        for extending Horizon's cababilities externally and for testing
        purposes.

    References
    ----------
    .. [Horizon_ISMRM19] Garyfallidis E., M-A. Cote, B.Q. Chandio,
        S. Fadnavis, J. Guaje, R. Aggarwal, E. St-Onge, K.S. Juneja,
        S. Koudoro, D. Reagan, DIPY Horizon: fast, modular, unified and
        adaptive visualization, Proceedings of: International Society of
        Magnetic Resonance in Medicine (ISMRM), Montreal, Canada, 2019.
    """

    hz = Horizon(tractograms, images, pams, cluster, cluster_thr,
                 random_colors, length_gt, length_lt, clusters_gt, clusters_lt,
                 world_coords, interactive, out_png, recorded_events,
                 return_showm, bg_color=bg_color,
                 order_transparent=order_transparent, buan=buan,
                 buan_colors=buan_colors, roi_images=roi_images,
                 roi_colors=roi_colors)

    scene = hz.build_scene()

    if return_showm:
        return hz.build_show(scene)
    hz.build_show(scene)
